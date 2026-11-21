"""Turn-local agent tools over the shared latest-only artifact storage.

Agent and manual edits use the same ChatStore compare-and-swap. An agent edit is always
applied to the content it loaded in the same turn, so manual edits are never silently lost.
"""
import json
import re
import unicodedata
from uuid import UUID

from google.genai import types
from pydantic import Field, ValidationError, model_validator
from sqlalchemy import select

from app.models.chat import ChatArtifact, ChatMessage

from .schemas import ARTIFACT_MAX_CHARS, Artifact, ArtifactType, Contract, Title
from .store import ChatError, artifact_view


def plain(text):
    """Quotation comparison form: case, whitespace and Polish diacritics do not matter
    (people often type without them, and the model restores them when quoting)."""
    text = unicodedata.normalize("NFKD", text.replace("ł", "l").replace("Ł", "L"))
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).casefold().split())

MISSING = "Do uzupełnienia."
APPLICATION_NOTE = "> Roboczy szkic zgłoszenia innowacji do Radaru. Nic nie zostało wysłane ani ocenione przez PCI."
SECTIONS = {
    "idea_card": ["Nazwa i podsumowanie", "Problem", "Rozwiązanie", "Odbiorcy", "Nowość", "Etap rozwoju i dowody",
                  "Znane ograniczenia", "Brakujące informacje"],
    "application_draft": ["Instytucja i twórcy", "Problem", "Rozwiązanie", "Odbiorcy i potencjalni wdrażający",
                          "Nowość i podobne rozwiązania", "Etap rozwoju i dowody", "Ochrona i prawa",
                          "Cel i potrzebne wsparcie", "Brakujące informacje"],
    "adaptation_plan": ["Wybrana innowacja", "Organizacja wdrażająca i jej potrzeba", "Zachowane elementy",
                        "Niezbędne dostosowania", "Zasoby i partnerzy", "Pilotaż i mierniki sukcesu", "Ryzyka", "Niewiadome"],
}
TYPE_NAMES = {"idea_card": "karta innowacji", "application_draft": "zgłoszenie do Radaru", "adaptation_plan": "plan wdrożenia"}
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
UUID_PATTERN = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"


def key(text):
    return re.sub(r"[\W_]+", " ", text.lower()).strip()


def headings(lines):
    """(index, level, normalized text) of Markdown headings outside fenced code."""
    fenced = False
    for i, line in enumerate(lines):
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
        elif not fenced and (match := HEADING.match(line)):
            yield i, len(match[1]), key(match[2])


def same(a, b):
    return a == b or a.startswith(b + " ") or b.startswith(a + " ")


def assemble(artifact_type, sections):
    """Canonical Markdown: every standard section in order, empty ones explicitly incomplete."""
    given = [(key(s.heading.strip().lstrip("#")), s.heading.strip().lstrip("#").strip(), s.content.strip()) for s in sections]
    used, blocks = set(), [APPLICATION_NOTE] if artifact_type == "application_draft" else []
    for name in SECTIONS[artifact_type]:
        match = next((i for i, (k, _, _) in enumerate(given) if i not in used and same(k, key(name))), None)
        used.add(match)
        blocks.append(f"## {name}\n\n{(given[match][2] if match is not None else '') or MISSING}")
    blocks += [f"## {title}\n\n{body or MISSING}" for i, (_, title, body) in enumerate(given) if i not in used]
    return "\n\n".join(blocks) + "\n"


def replace_section(markdown, heading, body):
    """Replace one section body until the next heading of the same or higher level."""
    lines = markdown.rstrip("\n").splitlines()
    found = list(headings(lines))
    for n, (index, level, text) in enumerate(found):
        if same(text, key(heading)):
            end = next((i for i, lvl, _ in found[n + 1:] if lvl <= level), len(lines))
            lines[index + 1:end] = ["", *body.strip("\n").splitlines(), *([""] if end < len(lines) else [])]
            return "\n".join(lines) + "\n"
    return "\n".join(lines) + f"\n\n## {heading.strip().lstrip('#').strip()}\n\n{body.strip()}\n"


class Section(Contract):
    heading: str = Field(min_length=1, max_length=200, description="Exact standard section heading, e.g. 'Problem'. One entry per section.")
    content: str = Field(max_length=ARTIFACT_MAX_CHARS, description="Polish Markdown body of this section only, without the heading; never content of another section. Empty if unknown.")


class QuotedEvidence(Contract):
    source_id: str
    quote: str = Field(min_length=1, max_length=1500)


class DraftSection(Contract):
    heading: str = Field(min_length=1, max_length=200)
    user_facts: list[str] = Field(default_factory=list, max_length=6, description="EXACT short quotations from the latest user statements supporting this section. Never invent confirmations or use superseded figures.")
    documented_facts: list[QuotedEvidence] = Field(default_factory=list, max_length=4, description="EXACT quotations from sources read this turn, with their IDs. No invented original rules or legal requirements.")
    proposals: list[str] = Field(default_factory=list, max_length=5, description="Qualitative AI suggestions only: NO numbers or calculations; use user_facts for quoted numbers. No assertions of cost/labor sufficiency, legal obligations, license permission or original rules.")
    unknowns: list[str] = Field(default_factory=list, max_length=8, description="Missing information; explicitly preserve unknown costs, IP and licence terms, partners, evidence and success measures. Do not declare missing documentation as a fact unless user confirmed it.")


SECTION_HELP = "; ".join(f"{t}: {', '.join(names)}" for t, names in SECTIONS.items())


class Create(Contract):
    type: ArtifactType
    title: Title
    sections: list[DraftSection] = Field(max_length=16, description=(
        "Content by standard section heading, in this order per type - " + SECTION_HELP + ". "
        "Fill only what the conversation or sources support; omitted sections are saved as 'Do uzupełnienia.'. "
        "Each fact must have an exact verified quotation. Proposals and unknowns are rendered separately."))
    innovation_id: str | None = Field(default=None, max_length=120, description="Exact real innovation ID retrieved or reloaded in this turn; required context for adaptation_plan when available.")
    evidence_ids: list[str] = Field(default_factory=list, max_length=20, description="IDs of sources or innovations actually read in this turn that support the content.")


class Get(Contract):
    artifact_id: str = Field(pattern=UUID_PATTERN)


class Update(Contract):
    artifact_id: str = Field(pattern=UUID_PATTERN)
    expected_revision: int = Field(ge=1, description="Revision returned by get_artifact in this turn.")
    sections: list[Section] = Field(default_factory=list, max_length=12, description="Preferred: replace only the requested sections (matched by heading; a new heading is appended); the rest of the current text stays intact.")
    content_markdown: str | None = Field(default=None, min_length=1, max_length=ARTIFACT_MAX_CHARS, description="Full replacement only when the user asked to rewrite the whole document.")
    title: Title | None = None
    evidence_ids: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def change(self):
        if not self.sections and self.content_markdown is None and self.title is None:
            raise ValueError("No change requested")
        return self


ARTIFACT_TOOL_NAMES = {"create_artifact", "get_artifact", "update_artifact"}
ARTIFACT_TOOLS = [types.Tool(function_declarations=[
    types.FunctionDeclaration(name=name, description=description, parameters_json_schema=model.model_json_schema())
    for name, description, model in [
        ("create_artifact", "Save a new editable draft in this conversation: idea_card (karta innowacji), application_draft "
         "(szkic zgłoszenia do Radaru, not sent or assessed) or adaptation_plan (plan wdrożenia innowacji). Only when the user asks "
         "for a draft or drafting intent is clear. Partial drafts are fine; missing standard sections are added as 'Do uzupełnienia.'", Create),
        ("get_artifact", "Load the current saved content and revision of a draft, including the user's manual edits. "
         "Required in this turn before update_artifact.", Get),
        ("update_artifact", "Apply the user's clear requested edit to a draft loaded in this turn. Change only the requested sections; "
         "keep all other text. On revision_conflict reload and reapply only if the request is still unambiguous.", Update),
    ]
])]


def sources_key(source):
    return (source.get("id"), source.get("url"), source.get("source_file"), source.get("page_start"))


class ArtifactTools:
    def __init__(self, store, turn, retrieval, sources, max_creates=3, selected_id=None):
        self.store, self.turn, self.retrieval, self.sources = store, turn, retrieval, sources
        self.selected_id = str(selected_id) if selected_id else None
        self.max_creates = max_creates
        self.loaded: dict[str, Artifact] = {}
        self.written = []
        self.created_count = 0
        self.recent: set[str] = set()
        self.committed: list[Artifact] = []  # Drained by the service into artifact_updated events.

    def evidence(self, ids):
        """Only metadata of sources read or retrieved in this turn; unknown IDs are rejected."""
        available = [s.model_dump(mode="json") for s in self.sources.sources]
        for _, _, candidate_sources in self.retrieval.candidates.values():
            available += [s.model_dump(mode="json") for s in candidate_sources]
        chosen = list({sources_key(s): s for s in available if s["id"] in ids}.values())
        unknown = set(ids) - {s["id"] for s in chosen}
        return chosen, unknown

    def commit(self, artifact):
        self.loaded[str(artifact.id)] = artifact
        self.written.append(artifact.title)
        if artifact.revision == 1:
            self.created_count += 1
        self.committed.append(artifact)
        return {"kind": "artifact", "status": "saved", "artifact": summary(artifact)}

    async def execute(self, name, arguments, max_bytes):
        try:
            if name == "create_artifact":
                return await self.create(Create.model_validate(arguments))
            if name == "get_artifact":
                return await self.get(Get.model_validate(arguments), max_bytes)
            return await self.update(Update.model_validate(arguments))
        except ValidationError:
            return {"kind": "artifact", "status": "invalid_arguments"}
        except ChatError as exc:
            if exc.error.code == "artifact_revision_conflict":
                self.loaded.pop(str(exc.error.current_artifact.id), None)
                return {"kind": "artifact", "status": "revision_conflict", "current_revision": exc.error.current_revision,
                        "message": "Dokument zmieniono w międzyczasie (np. ręcznie). Wczytaj go ponownie przez get_artifact "
                                   "i nanieś zmianę tylko jeśli prośba nadal jest jednoznaczna; w przeciwnym razie zapytaj użytkownika."}
            return {"kind": "artifact", "status": "not_found", "message": "Nie ma takiego dokumentu w tej rozmowie."}

    async def create(self, args):
        prepared = await self.prepare(args)
        if prepared["status"] != "prepared":
            return prepared
        return self.commit(await self.store.create_artifact(
            self.turn.conversation_id, type=args.type, title=args.title, content=prepared["content"],
            innovation_id=args.innovation_id, sources=prepared["sources"], message_id=self.turn.assistant_message_id))

    async def prepare(self, args):
        """Ground and render a draft independently of its artifact/matter storage."""
        if self.created_count >= self.max_creates:
            return {"kind": "artifact", "status": "limit", "message": "Limit nowych dokumentów w tej odpowiedzi."}
        if args.type == "application_draft":
            if self.retrieval.search_status is None:
                return {"kind": "artifact", "status": "comparison_required", "message":
                        "Najpierw search_innovations dla aktualnej innowacji, aby znaleźć podobne rozwiązania, następnie select_innovations dla kandydatów. Szkic może pozostać niepełny."}
            if self.retrieval.search_status == "ok" and not self.retrieval.selection_validated:
                return {"kind": "artifact", "status": "comparison_required", "message": "Oceń kandydatów select_innovations i wyjaśnij wynik porównania przed szkicem."}
        if args.innovation_id and args.innovation_id not in self.retrieval.candidates:
            return {"kind": "artifact", "status": "invalid_reference",
                    "message": "Najpierw odczytaj innowację przez get_innovation w tej turze albo pomiń innovation_id."}
        # The selected innovation always carries its own metadata, even without explicit evidence IDs.
        sources, unknown = self.evidence([*args.evidence_ids, *([m.id for m in self.retrieval.matches] if args.type == "application_draft" else []), *[q.source_id for s in args.sections for q in s.documented_facts], *([args.innovation_id] if args.innovation_id else [])])
        if unknown:
            return {"kind": "artifact", "status": "invalid_reference", "unknown_evidence_ids": sorted(unknown)}
        async with self.store.sessions() as db:
            from app.models.chat import ChatGuide
            guide = await db.get(ChatGuide, str(self.turn.conversation_id))
            started = (guide.data or {}).get("case_started_at") if guide else None
            query = select(ChatMessage.content).where(ChatMessage.conversation_id == str(self.turn.conversation_id), ChatMessage.role == "user")
            if started:
                from datetime import datetime
                # Retain this reset turn's user request as well.
                query = query.where((ChatMessage.created_at >= datetime.fromisoformat(started)) | (ChatMessage.id == str(self.turn.user_message_id)))
            user_messages = (await db.scalars(query.order_by(ChatMessage.position.desc()).limit(100))).all()
        evidence_text = {i: "\n".join(meta.card.model_dump().values()) + "\n" + "\n".join(e.text for e in self.retrieval.evidence.get(i, []))
                         for i, (meta, _, _) in self.retrieval.candidates.items()}
        evidence_text.update({p["source_id"]: "\n".join(e["text"] for e in p.get("passages", [])) for p in self.sources.evidence_packets})
        sections = []
        plain_messages = [plain(message) for message in user_messages]
        plain_evidence = {i: plain(text) for i, text in evidence_text.items()}
        for section in args.sections:
            # A statement without a matching quotation is never presented as a fact. It stays in the
            # draft for the user to confirm instead of rejecting the whole document, which made the
            # model retry blindly until the tool budget ran out.
            user_facts = [f for f in section.user_facts if plain(f) and any(plain(f) in m for m in plain_messages)]
            documented = [q for q in section.documented_facts if plain(q.quote) and plain(q.quote) in plain_evidence.get(q.source_id, "")]
            unconfirmed = [f for f in section.user_facts if f not in user_facts]
            unconfirmed += [q.quote for q in section.documented_facts if q not in documented]
            qualitative = [p for p in section.proposals if not re.search(r"[0-9=×]", p)]
            if len(qualitative) != len(section.proposals):
                section.unknowns.append("Liczbowe założenia propozycji nie zostały zweryfikowane i pominięto je w szkicu; wymagają uzupełnienia na podstawie danych.")
            body = ["Fakt użytkownika: " + fact for fact in user_facts]
            body += ["Z dokumentacji: " + q.quote for q in documented]
            body += ["Do potwierdzenia: " + text for text in unconfirmed]
            body += ["Propozycja AI: " + proposal for proposal in qualitative]
            body += ["Do ustalenia: " + unknown for unknown in section.unknowns]
            sections.append(Section(heading=section.heading, content="\n\n".join(body)))
        content = assemble(args.type, sections)
        content += "\n## Potwierdzenie wykonalności\n\nKoszt wdrożenia, warunki licencji lub transferu, prawa do rozwiązania i skuteczność w nowej organizacji wymagają osobnego potwierdzenia.\n"
        if args.type == "application_draft":
            if self.retrieval.search_status == "unavailable":
                comparison = "Wyszukiwanie innowacji było niedostępne. Nie sprawdzono podobieństwa; porównanie pozostaje do wykonania."
            elif self.retrieval.search_status == "empty":
                comparison = "Wyszukiwanie w dostępnej części bazy nie zwróciło kandydatów. Nie oznacza to braku podobnego rozwiązania poza tą bazą."
            elif not self.retrieval.matches:
                comparison = "Odczytanych kandydatów oceniono jako niepodobnych do zgłaszanej innowacji."
            else:
                comparison = "\n\n".join(f"{m.title}: {m.fit_reason}\nOgraniczenia: {'; '.join(m.limitations)}" for m in self.retrieval.matches)
            content += "\n## Podobne rozwiązania w bazie (ryzyko dublowania prac)\n\n" + comparison + "\n"

        if len(content) > ARTIFACT_MAX_CHARS:
            return {"kind": "artifact", "status": "too_large"}
        return {"kind": "artifact", "status": "prepared", "content": content, "sources": sources}

    async def get(self, args, max_bytes):
        async with self.store.sessions() as db:
            artifact = artifact_view(await self.store.artifact_row(db, self.turn.conversation_id, UUID(args.artifact_id)))
        result = {"kind": "artifact", "status": "ok", "artifact": {**summary(artifact), "content_markdown": artifact.content_markdown}}
        if len(json.dumps(result, ensure_ascii=False).encode()) > max_bytes:
            return {"kind": "artifact", "status": "too_large",
                    "message": "Dokument jest zbyt długi do edycji w czacie; poproś użytkownika o ręczną edycję."}
        self.loaded[str(artifact.id)] = artifact
        return result

    async def update(self, args):
        if self.selected_id and args.artifact_id != self.selected_id:
            return {"kind": "artifact", "status": "not_selected", "selected_artifact_id": self.selected_id,
                    "message": "Użytkownik wskazał inny dokument. Zmieniaj tylko wskazany albo zapytaj użytkownika."}
        if not self.selected_id and (others := await self.ambiguous(args.artifact_id)):
            return {"kind": "artifact", "status": "ambiguous", "candidates": others,
                    "message": "Jest kilka dokumentów tego typu. Nic nie zmieniono; zapytaj użytkownika, który dokument zmienić."}
        current = self.loaded.get(args.artifact_id)
        if current is None or current.revision != args.expected_revision:
            return {"kind": "artifact", "status": "read_required",
                    "message": "Najpierw wczytaj aktualną treść przez get_artifact w tej turze i użyj jej rewizji."}
        sources, unknown = self.evidence(args.evidence_ids)
        if unknown:
            return {"kind": "artifact", "status": "invalid_reference", "unknown_evidence_ids": sorted(unknown)}
        content = args.content_markdown if args.content_markdown is not None else current.content_markdown
        for change in args.sections:
            content = replace_section(content, change.heading, change.content)
        if len(content) > ARTIFACT_MAX_CHARS:
            return {"kind": "artifact", "status": "too_large"}
        merged = [s.model_dump(mode="json") for s in current.sources]
        merged += [s for s in sources if sources_key(s) not in {sources_key(m) for m in merged}]
        return self.commit(await self.store.write_artifact(
            self.turn.conversation_id, current.id, current.revision, content=content, title=args.title,
            sources=merged, message_id=self.turn.assistant_message_id))


    async def ambiguous(self, artifact_id):
        """Without a UI selection, another draft of the same type makes the target unclear,
        unless this draft is the one the previous reply or this turn worked on."""
        if any(str(a.id) == artifact_id for a in self.committed) or artifact_id in self.recent:
            return []
        async with self.store.sessions() as db:
            rows = (await db.scalars(select(ChatArtifact).where(ChatArtifact.conversation_id == self.turn.conversation_id))).all()
            previous = await db.scalar(select(ChatMessage).where(
                ChatMessage.conversation_id == self.turn.conversation_id, ChatMessage.role == "assistant",
                ChatMessage.id != self.turn.assistant_message_id, ChatMessage.position > 0,
            ).order_by(ChatMessage.position.desc()).limit(1))
        self.recent = set(previous.__dict__.get("artifact_links") or []) if previous else set()
        target = next((row for row in rows if row.id == artifact_id), None)
        if target is None or artifact_id in self.recent:
            return []
        same_type = [row for row in rows if row.type == target.type]
        return [{"artifact_id": row.id, "title": row.title} for row in same_type] if len(same_type) > 1 else []


def summary(artifact):
    return {"artifact_id": str(artifact.id), "type": artifact.type, "title": artifact.title, "revision": artifact.revision,
            "innovation_id": artifact.innovation_id}


def consumed_artifact(result):
    """Drop document text once Gemini has consumed it; get_artifact reloads when needed."""
    reduced = {"kind": "artifact", "status": result.get("status"), "consumed": True}
    if "artifact" in result:
        reduced["artifact"] = {k: v for k, v in result["artifact"].items() if k != "content_markdown"}
    return reduced


def artifact_note(artifacts):
    """Per-turn system context: current drafts (metadata only, content via get_artifact)."""
    if not artifacts:
        return " W tej rozmowie nie ma jeszcze zapisanych dokumentów."
    rows = [{**summary(a), "type_name": TYPE_NAMES[a.type]} for a in artifacts]
    return " Aktualne zapisane dokumenty tej rozmowy (najnowsze treści wczytuj get_artifact): " + json.dumps(rows, ensure_ascii=False) + "."


def selection_note(artifact):
    """Attached to the current user message only; never persisted."""
    return (f"[Użytkownik wskazał w interfejsie dokument: {TYPE_NAMES[artifact.type]} \"{artifact.title}\" "
            f"(artifact_id={artifact.id}). Polecenia zmiany w tej wiadomości dotyczą wyłącznie tego dokumentu.]")
