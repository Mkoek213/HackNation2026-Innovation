"""Text extraction with page provenance.

PDF: PyMuPDF text blocks in reading order (sort=True), one block ~ one paragraph.
DOCX: paragraphs with heading styles; DOCX has no page numbers.
Pages without a text layer (scans) are reported, not OCR-ed -- OCR needs Tesseract,
which is not part of the image yet.
"""
import logging
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

import docx
import pymupdf

from .schemas import DocType

logger = logging.getLogger(__name__)

SUPPORTED_SUFFIXES = {".pdf", ".docx"}


@dataclass(frozen=True)
class Block:
    text: str
    page: int | None  # 1-based physical PDF page; None for DOCX
    is_heading: bool


@dataclass(frozen=True)
class ExtractedDocument:
    path: Path
    doc_type: DocType
    blocks: list[Block]


# Section headings: "II. Opis", "IV.Elementy", "2.1 Wyniki". Plain "2." is usually a list item.
_HEADING_RE = re.compile(r"^(?:[IVX]{1,5}\.|\d+\.\d+(?:\.\d+)*\.?)\s*[A-ZĄĆĘŁŃÓŚŹŻ]")
_LIST_ITEM_RE = re.compile(r"^(?:\d+\.|[a-z]\)|[-•–])\s")
_WS_RE = re.compile(r"[ \t ]+")
_HYPHEN_BREAK_RE = re.compile(r"(\w)-\n(\w)")


def guess_doc_type(path: Path) -> DocType:
    name = path.stem.lower().replace("_", "-").replace(" ", "-")
    if "patent" in name or "zgloszeni" in name:
        return "patent"
    if "publikacj" in name or "artykul" in name:
        return "publikacja"
    if "raport" in name or "sprawozdani" in name:
        return "raport"
    if "prezentacj" in name or "folder" in name or "ulotk" in name:
        return "prezentacja"
    if "instrukcj" in name:
        return "instrukcja"
    return "material"


def _clean(text: str) -> str:
    text = _HYPHEN_BREAK_RE.sub(r"\1\2", text)
    text = text.replace("\n", " ")
    return _WS_RE.sub(" ", text).strip()


def _looks_like_heading(text: str) -> bool:
    if len(text) > 100 or text.endswith((".", ",", ";", ":")):
        return False
    if _HEADING_RE.match(text):
        return True
    if _LIST_ITEM_RE.match(text):
        return False
    letters = [c for c in text if c.isalpha()]
    return len(text) <= 80 and len(letters) >= 4 and all(c.isupper() for c in letters)


def extract_pdf(path: Path) -> list[Block]:
    blocks: list[Block] = []
    with pymupdf.open(path) as pdf:
        for page_index, page in enumerate(pdf, start=1):
            for b in page.get_text("blocks", sort=True):
                if b[6] != 0:  # image block
                    continue
                text = _clean(b[4])
                # Drop page numbers and dotted table-of-contents lines.
                if not text or text.isdigit() or re.search(r"_{5,}|\.{5,}", text):
                    continue
                blocks.append(Block(text=text, page=page_index, is_heading=_looks_like_heading(text)))
    return blocks


def extract_docx(path: Path) -> list[Block]:
    blocks: list[Block] = []
    for p in docx.Document(str(path)).paragraphs:
        text = _clean(p.text)
        if not text:
            continue
        style = (p.style.name or "").lower() if p.style is not None else ""
        is_heading = style.startswith(("heading", "nagłówek", "title", "tytuł")) or _looks_like_heading(text)
        blocks.append(Block(text=text, page=None, is_heading=is_heading))
    return blocks


def extract(path: Path) -> ExtractedDocument | None:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        blocks = extract_pdf(path)
    elif suffix == ".docx":
        blocks = extract_docx(path)
    else:
        return None
    if sum(len(b.text) for b in blocks) < 200:
        logger.warning("No usable text layer in %s (scan? OCR not configured)", path.name)
        return None
    return ExtractedDocument(path=path, doc_type=guess_doc_type(path), blocks=blocks)


def expand_archives(paths: list[Path], workdir: Path, *, max_bytes: int = 100 * 1024 * 1024) -> list[Path]:
    """Unpack .zip uploads (and zips nested inside them) into workdir;
    returns the flat list of candidate files."""
    out: list[Path] = []
    queue = [(p, 0) for p in paths]
    total = 0
    entries = 0
    n = 0
    while queue:
        path, depth = queue.pop(0)
        if path.suffix.lower() != ".zip":
            out.append(path)
            continue
        if depth >= 5:
            raise ValueError("Archiwum przekracza limit zagnieżdżenia (5).")
        n += 1
        target = workdir / f"{n}-{path.stem}"
        with zipfile.ZipFile(path) as zf:
            for index, member in enumerate(zf.infolist()):
                entries += 1
                if entries > 1000:
                    raise ValueError("Archiwum przekracza limit liczby plików (1000).")
                member_path = Path(member.filename)
                # Zip-slip guard: only plain relative paths inside the target dir.
                if member.is_dir() or member_path.is_absolute() or ".." in member_path.parts:
                    continue
                if member_path.suffix.lower() not in SUPPORTED_SUFFIXES | {".zip"}:
                    continue
                if member.file_size > max_bytes or total + member.file_size > max_bytes:
                    raise ValueError("Archiwum przekracza limit rozmiaru po rozpakowaniu.")
                # Separate member directories preserve duplicate names without overwriting bytes.
                dest = target / str(index) / member_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, open(dest, "wb") as dst:
                    size = 0
                    while chunk := src.read(1024 * 1024):
                        size += len(chunk)
                        total += len(chunk)
                        if size > max_bytes or total > max_bytes:
                            raise ValueError("Archiwum przekracza limit rozmiaru po rozpakowaniu.")
                        dst.write(chunk)
                queue.append((dest, depth + 1))
    return out


def dedupe_formats(paths: list[Path]) -> list[Path]:
    """Sources often publish the same report as PDF and DOCX. Keep the PDF (page numbers
    for citations) and drop the DOCX twin with the same stem."""
    pdf_stems = {p.stem.lower() for p in paths if p.suffix.lower() == ".pdf"}
    return [p for p in paths if not (p.suffix.lower() == ".docx" and p.stem.lower() in pdf_stems)]
