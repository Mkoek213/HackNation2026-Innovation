"""Render a titled Markdown document to a downloadable PDF (Polish text via HTML)."""

from __future__ import annotations

import html
import re
import unicodedata
from io import BytesIO

import pymupdf

MAX_TITLE = 200
MAX_CONTENT = 120_000


def _inline(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    return escaped


def markdown_to_html(title: str, content: str) -> str:
    """Minimal Markdown → HTML for Radar draft cards (headings, lists, paragraphs)."""
    blocks: list[str] = [f"<h1>{html.escape(title.strip() or 'Dokument')}</h1>"]
    paragraph: list[str] = []
    list_items: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            blocks.append(f"<p>{_inline(' '.join(paragraph))}</p>")
            paragraph = []

    def flush_list() -> None:
        nonlocal list_items
        if list_items:
            blocks.append("<ul>" + "".join(f"<li>{item}</li>" for item in list_items) + "</ul>")
            list_items = []

    for raw in content.replace("\r\n", "\n").split("\n"):
        line = raw.rstrip()
        if not line.strip():
            flush_paragraph()
            flush_list()
            continue
        if line.startswith("### "):
            flush_paragraph()
            flush_list()
            blocks.append(f"<h3>{_inline(line[4:].strip())}</h3>")
        elif line.startswith("## "):
            flush_paragraph()
            flush_list()
            blocks.append(f"<h2>{_inline(line[3:].strip())}</h2>")
        elif line.startswith("# "):
            flush_paragraph()
            flush_list()
            blocks.append(f"<h2>{_inline(line[2:].strip())}</h2>")
        elif line.startswith(">"):
            flush_paragraph()
            flush_list()
            blocks.append(f"<p><i>{_inline(line.lstrip('> ').strip())}</i></p>")
        elif re.match(r"^[-*]\s+", line):
            flush_paragraph()
            list_items.append(_inline(re.sub(r"^[-*]\s+", "", line)))
        else:
            flush_list()
            paragraph.append(line.strip())
    flush_paragraph()
    flush_list()
    return (
        "<div style='font-family:sans-serif;font-size:11pt;line-height:1.45;color:#1a2433'>"
        + "".join(blocks)
        + "</div>"
    )


def render_markdown_pdf(title: str, content: str) -> bytes:
    """Return PDF bytes for a titled Markdown body. Truncates oversized input."""
    title = (title or "Dokument").strip()[:MAX_TITLE] or "Dokument"
    content = (content or "").strip()[:MAX_CONTENT] or "_(Brak treści)_"
    page_html = markdown_to_html(title, content)
    mediabox = pymupdf.paper_rect("a4")
    content_box = mediabox + (48, 48, -48, -48)

    def rectfn(_rect_num: int, _filled: float):
        return mediabox, content_box, pymupdf.Identity

    buffer = BytesIO()
    writer = pymupdf.DocumentWriter(buffer)
    story = pymupdf.Story(html=page_html)
    story.write(writer, rectfn)
    writer.close()
    return buffer.getvalue()


def pdf_filename(title: str) -> str:
    # Content-Disposition headers require an ASCII-safe fallback filename.
    normalized = unicodedata.normalize("NFKD", title.replace("ł", "l").replace("Ł", "L"))
    ascii_title = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9\-]+", "-", ascii_title.strip().lower()).strip("-")[:80]
    return f"{slug or 'dokument'}.pdf"
