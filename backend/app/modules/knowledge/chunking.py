"""Section-aware chunking.

Blocks are accumulated until ~max_chars; a heading starts a new chunk once the
current one is big enough to stand alone. Each chunk remembers the nearest heading
and its page span so answers can cite "model końcowy, s. 15-16".
Sizes are in characters: ~2000 chars of Polish prose is roughly 500 tokens, which
stays under e5's 512-token window together with the context header.
"""
from dataclasses import dataclass

from .extract import Block


@dataclass(frozen=True)
class Chunk:
    text: str
    section: str | None
    page_start: int | None
    page_end: int | None


def chunk_blocks(
        blocks: list[Block],
        *,
        max_chars: int = 1800,
        min_chars: int = 800,
        overlap_blocks: int = 1,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    current: list[Block] = []
    section: str | None = None
    current_section: str | None = None

    def size(bs: list[Block]) -> int:
        return sum(len(b.text) + 1 for b in bs)

    def flush(keep_overlap: bool) -> list[Block]:
        if not current:
            return []
        pages = [b.page for b in current if b.page is not None]
        chunks.append(Chunk(
            text="\n".join(b.text for b in current),
            section=current_section,
            page_start=min(pages) if pages else None,
            page_end=max(pages) if pages else None,
        ))
        # Carry the last non-heading block(s) over for continuity within a section.
        return [b for b in current[-overlap_blocks:] if not b.is_heading] if keep_overlap else []

    for block in blocks:
        if block.is_heading:
            if size(current) >= min_chars:
                current = flush(keep_overlap=False)
            section = block.text
            if not current:
                current_section = section
            current.append(block)
            continue

        # Split oversized single blocks (e.g. a whole page extracted as one block).
        pieces = [block.text[i:i + max_chars] for i in range(0, len(block.text), max_chars)] or [block.text]
        for piece in pieces:
            piece_block = Block(text=piece, page=block.page, is_heading=False)
            if current and size(current) + len(piece) > max_chars:
                current = flush(keep_overlap=True)
                current_section = section
            if not current:
                current_section = section
            current.append(piece_block)

    flush(keep_overlap=False)
    return chunks
