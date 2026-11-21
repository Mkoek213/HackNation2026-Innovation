"""Private, ephemeral PDF export of owner-reviewed plain text; no remote resources."""
from html import escape
from io import BytesIO
import re

import pymupdf
from fastapi import HTTPException

CSS = """
body { font-family: sans-serif; font-size: 10.5pt; line-height: 1.5; color: #1A2433; }
h1 { font-size: 19pt; color: #16325C; margin-bottom: 18pt; }
h2 { font-size: 13pt; color: #16325C; margin-top: 18pt; margin-bottom: 8pt; page-break-after: avoid; }
p { margin-top: 0; margin-bottom: 7pt; }
"""


def render_pdf(title, packet):
    # Escape every character: edited content must never become HTML, links, or file reads.
    blocks = [f"<h1>{escape(title)}</h1>"]
    for paragraph in packet.split("\n\n"):
        lines = paragraph.splitlines()
        for line in lines:
            if not line.strip():
                continue
            heading = line.startswith("#") or (line.isupper() and len(line) < 160)
            tag = "h2" if heading else "p"
            text = line.lstrip("# ") if heading else line
            # Soft opportunities also wrap long URLs and uninterrupted input safely.
            text = re.sub(r"\S{46,}", lambda m: "\u200b".join(m[0][i:i + 45] for i in range(0, len(m[0]), 45)), text)
            blocks.append(f"<{tag}>{escape(text)}</{tag}>")
    output = BytesIO()
    writer = pymupdf.DocumentWriter(output)
    page_rect = pymupdf.Rect(0, 0, 595, 842)

    # Lay out each heading with its first paragraph as one block. Retry a block
    # on a fresh page when it would split, so headings never hang at the foot.
    groups = []
    for block in blocks:
        if groups and groups[-1].endswith(("</h1>", "</h2>")):
            groups[-1] += block
        else:
            groups.append(block)
    device = None
    page_number, top = 0, 48

    def begin_page():
        nonlocal device, page_number, top
        if device is not None:
            writer.end_page()
        if page_number >= 80:
            raise HTTPException(413, "Podsumowanie jest zbyt długie. Skróć treść PDF i spróbuj ponownie.")
        device = writer.begin_page(page_rect)
        page_number += 1
        top = 48

    try:
        begin_page()
        for group in groups:
            story = pymupdf.Story("<html><body>" + group + "</body></html>", user_css=CSS)
            more, filled = story.place(pymupdf.Rect(48, top, 547, 790))
            if more and top > 48:
                story.reset()
                begin_page()
                more, filled = story.place(pymupdf.Rect(48, top, 547, 790))
            story.draw(device)
            while more:
                begin_page()
                more, filled = story.place(pymupdf.Rect(48, top, 547, 790))
                story.draw(device)
            top = pymupdf.Rect(filled).y1 + 3
        writer.end_page()
        device = None
    finally:
        writer.close()
    with pymupdf.open(stream=output.getvalue(), filetype="pdf") as document:
        document.set_metadata({"title": title, "subject": "Materiał do konsultacji z PCI", "creator": "Radar innowacji - podsumowanie sprawy"})
        for n, page in enumerate(document):
            page.insert_text((48, 816), f"Radar innowacji | {n + 1} / {len(document)}", fontsize=9, color=(0.29, 0.33, 0.41))
        return document.tobytes(garbage=4, deflate=True)
