"""Live, turn-local reading of approved public innovation sources.

Fetched bytes, extracted text and passages live only inside one SourceTools instance
(one turn) and are never written to disk, logs or the database. Only SourceMetadata
(title, URL, pages, year, geography, fetch time) leaves this module for persistence.
"""
import asyncio
import hashlib
import ipaddress
import json
import re
import socket
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
import lxml.html
import pymupdf
from google.genai import types
from pydantic import Field, ValidationError

from .schemas import Contract, SourceMetadata


@dataclass(frozen=True)
class Entry:
    id: str
    url: str
    title: str
    note: str  # Scope caveat passed to the model with every read.
    host: str
    prefixes: tuple[str, ...]  # Allowed URL paths on the host; every fetch and redirect hop is checked.

    def allows(self, url):
        parts = urlsplit(url)
        return parts.hostname == self.host and any(parts.path.startswith(p) for p in self.prefixes)


ENTRIES = {e.id: e for e in [
    Entry("interreg_projects", "https://interreg.gov.pl/lista-projektow/", "Lista projektów Interreg",
        "Opisy projektów współpracy międzynarodowej; stan i rezultaty sprawdź u źródła.",
        "interreg.gov.pl", ("/lista-projektow", "/projekt", "/wp-content/uploads/")),
    Entry("ncbr_successes", "https://www.gov.pl/web/ncbr/wyszukiwarka-sukcesow-beneficjentow",
        "Wyszukiwarka sukcesów beneficjentów NCBR",
        "Opisy projektów B+R finansowanych przez NCBR; wyniki komercjalizacji podawaj tylko z odczytanego opisu.",
        "www.gov.pl", ("/web/ncbr/",)),
    Entry("pci", "https://pcinn.org/", "Podkarpackie Centrum Innowacji",
        "Oferta, programy i aktualności PCI; warunki programów sprawdź u źródła.",
        "pcinn.org", ("/",)),
]}


class SourceError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


def normalize(url):
    parts = urlsplit(url)
    scheme = "https" if parts.scheme in ("http", "https") else parts.scheme
    return urlunsplit((scheme, (parts.hostname or "").lower(), parts.path or "/", parts.query, ""))


def stable_id(url):
    return "src-" + hashlib.sha256(url.encode()).hexdigest()[:12]


async def public_host(host):
    infos = await asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            raise SourceError("disallowed", "Adres źródła nie jest publiczny.")


class Fetcher:
    """Bounded HTTPS fetches; every hop is checked against the entry scope."""

    def __init__(self, timeout, max_bytes):
        self.timeout, self.max_bytes = timeout, max_bytes
        self.client = httpx.AsyncClient(follow_redirects=False, timeout=timeout,
                                        headers={"User-Agent": "RadarInnowacjiChat/1.0"})

    async def fetch(self, entry, url, *, data=None):
        for _ in range(4):
            url = normalize(url)
            parts = urlsplit(url)
            if parts.scheme != "https" or parts.port not in (None, 443) or not entry.allows(url):
                raise SourceError("disallowed", "Ten adres jest poza zatwierdzonym zakresem źródeł.")
            await public_host(parts.hostname)
            request = self.client.build_request("POST" if data else "GET", url, data=data)
            response = await self.client.send(request, stream=True)
            try:
                if response.is_redirect:
                    url, data = urljoin(url, response.headers.get("location", "")), None
                    continue
                if response.status_code != 200:
                    raise SourceError("unavailable", f"Źródło odpowiedziało kodem {response.status_code}.")
                kind = response.headers.get("content-type", "").split(";")[0].strip().lower()
                if kind not in ("text/html", "application/pdf"):
                    raise SourceError("unsupported", "Nieobsługiwany format pliku (obsługiwane: HTML, PDF).")
                if int(response.headers.get("content-length") or 0) > self.max_bytes:
                    raise SourceError("too_large", "Plik przekracza limit rozmiaru odczytu.")
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body += chunk
                    if len(body) > self.max_bytes:
                        raise SourceError("too_large", "Plik przekracza limit rozmiaru odczytu.")
                return url, kind, bytes(body), response.encoding or "utf-8", response.headers.get("content-disposition", "")
            finally:
                await response.aclose()
        raise SourceError("disallowed", "Zbyt wiele przekierowań.")

    async def aclose(self):
        await self.client.aclose()


def stems(text):
    # Five-letter prefixes roughly absorb Polish inflection without a stemmer.
    return {w[:5] for w in re.findall(r"\w{3,}", text.lower()) if not w.isdigit()} | set(re.findall(r"\b\d{4}\b", text))


def score(query_stems, text):
    lowered = text.lower()
    return sum(lowered.count(s) for s in query_stems)


def html_doc(body, encoding):
    return lxml.html.document_fromstring(body.decode(encoding, errors="replace"))


def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def content_root(doc):
    for xpath in ('//div[contains(@class,"content__main")]', '//*[@id="content"]', "//body"):
        found = doc.xpath(xpath)
        if found:
            return found[0]
    return doc


@dataclass
class Handle:
    entry_id: str
    url: str
    title: str


@dataclass
class SourceTools:
    timeout: int = 15
    max_bytes: int = 10_000_000
    handles: dict = field(default_factory=dict)
    sources: list = field(default_factory=list)
    evidence_packets: list = field(default_factory=list)

    def __post_init__(self):
        self.fetcher = Fetcher(self.timeout, self.max_bytes)
        for entry_id, entry in ENTRIES.items():
            self.handles[entry_id] = Handle(entry_id, entry.url, entry.title)

    async def aclose(self):
        await self.fetcher.aclose()

    def remember(self, entry_id, url, title):
        handle = stable_id(normalize(url))
        self.handles.setdefault(handle, Handle(entry_id, normalize(url), clean(title)[:300] or "Dokument"))
        return handle

    def record(self, handle, *, pages=None, year=None, geography=None):
        meta = SourceMetadata(id=stable_id(handle.url), title=handle.title, url=handle.url,
                              page_start=pages[0] if pages else None, page_end=pages[1] if pages else None,
                              publication_date=year, geography=geography, fetched_at=datetime.now(timezone.utc))
        self.sources = [s for s in self.sources if s.id != meta.id] + [meta]

    async def execute(self, name, arguments, max_bytes):
        try:
            if name == "discover_sources":
                args = Discover.model_validate(arguments)
                return await asyncio.wait_for(self.discover(args), self.timeout * 2)
            args = Read.model_validate(arguments)
            result = fit(await asyncio.wait_for(self.read(args), self.timeout * 3), max_bytes)
            if result.get("status") == "ok":
                self.evidence_packets.append(result)
            return result
        except ValidationError:
            return {"kind": "source", "status": "invalid_arguments"}
        except SourceError as exc:
            return {"kind": "source", "status": exc.status, "message": exc.message}
        except (TimeoutError, httpx.HTTPError, OSError):
            return {"kind": "source", "status": "unavailable", "message": "Nie udało się odczytać źródła. Nie podawaj faktów z tego źródła."}
        except Exception:
            return {"kind": "source", "status": "extraction_failed", "message": "Nie udało się odczytać treści źródła."}

    def resolve(self, source_id):
        handle = self.handles.get(source_id)
        if handle is None:
            raise SourceError("invalid_reference", "Nieznany identyfikator źródła. Użyj discover_sources w tej turze.")
        return handle, ENTRIES[handle.entry_id]

    async def discover(self, args):
        handle, entry = self.resolve(args.source_id)
        url, kind, body, encoding, _ = await self.fetcher.fetch(entry, handle.url)
        if kind != "text/html":
            raise SourceError("not_an_index", "To jest dokument, odczytaj go przez read_source.")
        doc = html_doc(body, encoding)
        root = content_root(doc)
        links = {}
        for anchor in root.xpath(".//a[@href]"):
            target = normalize(urljoin(url, anchor.get("href")))
            title = clean(anchor.text_content()) or clean(anchor.get("title"))
            if target == normalize(url) or not entry.allows(target) or target.endswith(".zip"):
                continue
            if title and len(title) > len(links.get(target, "")) and title.lower() not in ("więcej", "pobierz"):
                links[target] = title
            else:
                links.setdefault(target, title or urlsplit(target).path.rsplit("/", 1)[-1])
        query = stems(args.query or "")
        ranked = sorted(links.items(), key=lambda item: -score(query, item[1] + " " + item[0]) if query else 0)
        found = [{"source_id": self.remember(handle.entry_id, u, t), "title": t} for u, t in ranked[:args.limit]]
        return {"kind": "source", "status": "ok" if found else "empty", "entry": handle.title, "links": found,
                "note": "To są wyłącznie tytuły i odnośniki. Aby podać fakty, odczytaj dokument przez read_source."}

    async def read(self, args):
        handle, entry = self.resolve(args.source_id)
        if args.source_id in ENTRIES:
            raise SourceError("index_only", f"{args.source_id} to indeks. Najpierw wywołaj discover_sources(source_id=\"{args.source_id}\", query=...), potem read_source na zwróconym source_id.")
        _, kind, body, encoding, disposition = await self.fetcher.fetch(entry, handle.url)
        query = stems(args.query or "")
        if kind == "application/pdf":
            passages, total, title = await asyncio.to_thread(pdf_passages, body)
        else:
            passages, total, title = html_passages(body, encoding), 1, None
        del body
        if sum(len(p["text"]) for p in passages) < 200:
            raise SourceError("no_text", "Dokument nie zawiera tekstu do odczytu (np. skan). Brak dowodu z tego źródła.")
        if title and handle.title in ("Dokument", ""):
            handle.title = title[:300]
        year = re.match(r"\s*(\d{4})\b", handle.title) or re.search(r"\b(20\d{2})\b", disposition)
        ranked = sorted(passages, key=lambda p: -score(query, p["text"])) if query else passages
        if query and score(query, ranked[0]["text"]) == 0:
            ranked = passages  # No match: show the opening (title, summary, contents).
        pages = [p["page"] for p in ranked[:args.max_passages] if p["page"]]
        self.record(handle, pages=(min(pages), max(pages)) if pages else None, year=year.group(1) if year else None)
        return {"kind": "source", "status": "ok", "source_id": args.source_id, "title": handle.title, "url": handle.url,
                "pages_total": total, "year": year.group(1) if year else None, "note": entry.note,
                "passages": ranked[:args.max_passages]}


def pdf_passages(body):
    with pymupdf.open(stream=body, filetype="pdf") as doc:
        passages = []
        for number in range(1, doc.page_count + 1):
            text = clean(doc[number - 1].get_text())
            for start in range(0, len(text), 900):
                if len(text[start:start + 900]) > 40:
                    passages.append({"page": number, "text": text[start:start + 900]})
        return passages, doc.page_count, clean((doc.metadata or {}).get("title") or "") or None


def html_passages(body, encoding):
    root = content_root(html_doc(body, encoding))
    for junk in root.xpath(".//script|.//style|.//nav"):
        junk.drop_tree()
    text = clean(root.text_content())
    return [{"page": None, "text": text[i:i + 900]} for i in range(0, len(text), 900)]


def fit(result, max_bytes):
    """Keep the most relevant passages inside the per-call evidence budget."""
    size = lambda: len(json.dumps(result, ensure_ascii=False).encode())
    while result.get("passages") and size() > max_bytes:
        result["passages"].pop()
        result["truncated"] = True
    if size() > max_bytes:
        return {"kind": "source", "status": "evidence_budget_exceeded", "message": "Brak miejsca na treść źródła."}
    return result


def consumed_source(result):
    reduced = {"kind": "source", "status": result.get("status"), "consumed": True}
    if "links" in result:
        reduced["links"] = result["links"]  # Handles stay usable later in this turn.
    if "title" in result:
        reduced.update(source_id=result.get("source_id"), title=result["title"])
    return reduced


class Discover(Contract):
    source_id: str = Field(min_length=1, max_length=80, description="Entry ID (interreg_projects, ncbr_successes, pci) or a source_id of a discovered index page.")
    query: str | None = Field(default=None, max_length=300, description="Keywords used to rank the discovered links.")
    limit: int = Field(default=15, ge=1, le=30)


class Read(Contract):
    source_id: str = Field(min_length=1, max_length=80, description="A source_id returned by discover_sources in this turn.")
    query: str | None = Field(default=None, max_length=300, description="What to look for inside the document; selects relevant passages.")
    max_passages: int = Field(default=5, ge=1, le=10)


SOURCE_TOOL_NAMES = {"discover_sources", "read_source"}
SOURCE_TOOLS = [types.Tool(function_declarations=[
    types.FunctionDeclaration(name="discover_sources", parameters_json_schema=Discover.model_json_schema(), description=(
        "List relevant links from an approved public source: interreg_projects (Interreg cooperation projects), "
        "ncbr_successes (R&D projects funded by NCBR), pci (Podkarpackie Centrum Innowacji programmes and news). "
        "Returns titles and source_id handles only; titles are not evidence.")),
    types.FunctionDeclaration(name="read_source", parameters_json_schema=Read.model_json_schema(), description=(
        "Read a discovered document/page live and return relevant passages with page numbers.")),
])]
