"""Two chunking strategies over parsed pages.

fixed      Sliding windows of CHUNK_TOKENS tokens (OVERLAP_TOKENS overlap) over the whole
           document's text. Ignores page, section and table boundaries: the baseline.
structure  Packs whole blocks of one page into chunks of at most CHUNK_TOKENS tokens.
           Never crosses a page, keeps a heading with the content after it, and keeps a
           table whole when it fits; larger tables split by rows with the header row
           repeated, larger paragraphs split at sentence ends.

Both strategies prepend the same metadata header (company, form, period, section) to the
text that gets embedded, so the comparison isolates the boundaries.
Token counts use the embedding model's own tokenizer.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from functools import lru_cache

from tokenizers import Tokenizer

from finrag import config
from finrag.corpus import DocMeta

CHUNK_TOKENS = 350
OVERLAP_TOKENS = 50
SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\"'])")


@lru_cache(maxsize=1)
def tokenizer() -> Tokenizer:
    return Tokenizer.from_pretrained(config.EMBED_MODEL, revision=config.EMBED_MODEL_REVISION)


def n_tokens(text: str) -> int:
    return len(tokenizer().encode(text, add_special_tokens=False).ids)


@dataclass
class Chunk:
    chunk_id: str
    strategy: str
    doc_name: str
    company: str
    doc_type: str
    fiscal_year: int
    fiscal_quarter: int | None
    period_label: str
    page_idx: int  # page holding most of the chunk (0-based, as in FinanceBench)
    pages: list[int]
    section: str | None
    subsection: str | None
    has_table: bool
    n_tokens: int
    text: str
    embed_text: str = field(default="")

    def to_dict(self) -> dict:
        return asdict(self)


def embed_header(meta: DocMeta, section: str | None, subsection: str | None) -> str:
    parts = [meta.header]
    if section:
        parts.append(section[:80])
    if subsection and subsection != section:
        parts.append(subsection[:80])
    return " | ".join(parts)


def _chunk(meta: DocMeta, strategy: str, i: int, pages: list[int], page_idx: int, section, subsection,
           has_table: bool, text: str) -> Chunk:
    header = embed_header(meta, section, subsection)
    return Chunk(
        chunk_id=f"{meta.doc_name}::{strategy}::{i:05d}", strategy=strategy, doc_name=meta.doc_name,
        company=meta.company, doc_type=meta.doc_type, fiscal_year=meta.fiscal_year,
        fiscal_quarter=meta.fiscal_quarter, period_label=meta.period_label, page_idx=page_idx,
        pages=pages, section=section, subsection=subsection, has_table=has_table,
        n_tokens=n_tokens(text), text=text, embed_text=f"{header}\n{text}",
    )


# ---------------------------------------------------------------- fixed-size


def fixed_chunks(meta: DocMeta, pages: list[dict]) -> list[Chunk]:
    """pages: [{"page_idx": int, "blocks": [{"kind","text","section","subsection"}]}]."""
    pieces: list[str] = []
    spans: list[tuple[int, int, int, dict]] = []  # (start, end, page_idx, block)
    pos = 0
    for page in pages:
        for block in page["blocks"]:
            if pieces:
                pieces.append("\n\n")
                pos += 2
            pieces.append(block["text"])
            spans.append((pos, pos + len(block["text"]), page["page_idx"], block))
            pos += len(block["text"])
    text = "".join(pieces)
    if not text:
        return []
    enc = tokenizer().encode(text, add_special_tokens=False)
    offsets = enc.offsets
    chunks: list[Chunk] = []
    stride = CHUNK_TOKENS - OVERLAP_TOKENS
    for i, start in enumerate(range(0, len(offsets), stride)):
        window = offsets[start:start + CHUNK_TOKENS]
        c0, c1 = window[0][0], window[-1][1]
        overlap: dict[int, int] = {}
        first_block = None
        has_table = False
        for s, e, page_idx, block in spans:
            covered = min(e, c1) - max(s, c0)
            if covered > 0:
                overlap[page_idx] = overlap.get(page_idx, 0) + covered
                first_block = first_block or block
                has_table = has_table or block["kind"] == "table"
        page_idx = max(overlap, key=overlap.get)
        chunks.append(_chunk(meta, "fixed", i, sorted(overlap), page_idx, first_block["section"],
                             first_block["subsection"], has_table, text[c0:c1]))
        if start + CHUNK_TOKENS >= len(offsets):
            break
    return chunks


# ---------------------------------------------------------------- structure-aware


def _split_table(markdown: str) -> list[str]:
    lines = markdown.split("\n")
    head, rows = lines[:2], lines[2:]
    parts: list[str] = []
    current: list[str] = []
    budget = CHUNK_TOKENS - n_tokens("\n".join(head))
    used = 0
    for row in rows:
        cost = n_tokens(row) + 1
        if current and used + cost > budget:
            parts.append("\n".join(head + current))
            current, used = [], 0
        current.append(row)
        used += cost
    if current:
        parts.append("\n".join(head + current))
    return parts


def _split_text(text: str) -> list[str]:
    parts: list[str] = []
    current = ""
    for sentence in SENTENCE_END.split(text):
        candidate = f"{current} {sentence}".strip()
        if current and n_tokens(candidate) > CHUNK_TOKENS:
            parts.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        parts.append(current)
    # A single sentence longer than the budget is cut by tokens as a last resort.
    out: list[str] = []
    for part in parts:
        enc = tokenizer().encode(part, add_special_tokens=False)
        if len(enc.ids) <= CHUNK_TOKENS:
            out.append(part)
            continue
        for s in range(0, len(enc.offsets), CHUNK_TOKENS):
            window = enc.offsets[s:s + CHUNK_TOKENS]
            out.append(part[window[0][0]:window[-1][1]])
    return out


def structure_chunks(meta: DocMeta, pages: list[dict]) -> list[Chunk]:
    chunks: list[Chunk] = []

    def emit(page_idx: int, items: list[dict]) -> None:
        content = [b for b in items if b["kind"] != "heading"] or items
        chunks.append(_chunk(meta, "structure", len(chunks), [page_idx], page_idx, content[0]["section"],
                             content[0]["subsection"], any(b["kind"] == "table" for b in items),
                             "\n\n".join(b["text"] for b in items)))

    for page in pages:
        units: list[dict] = []
        for block in page["blocks"]:
            if n_tokens(block["text"]) <= CHUNK_TOKENS:
                units.append(block)
                continue
            split = _split_table(block["text"]) if block["kind"] == "table" else _split_text(block["text"])
            units.extend({**block, "text": part} for part in split)

        buffer: list[dict] = []
        used = 0
        for unit in units:
            cost = n_tokens(unit["text"]) + 2
            if buffer and used + cost > CHUNK_TOKENS:
                # Do not leave headings stranded at the end of a chunk.
                carry: list[dict] = []
                while buffer and buffer[-1]["kind"] == "heading":
                    carry.insert(0, buffer.pop())
                if buffer:
                    emit(page["page_idx"], buffer)
                buffer = carry
                used = sum(n_tokens(b["text"]) + 2 for b in buffer)
            buffer.append(unit)
            used += cost
        if buffer:
            emit(page["page_idx"], buffer)
    return chunks


STRATEGIES = {"fixed": fixed_chunks, "structure": structure_chunks}
