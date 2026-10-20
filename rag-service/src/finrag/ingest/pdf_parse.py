"""Parse one filing PDF into pages of ordered blocks (heading / text / table).

Page indexes are 0-based, matching FinanceBench's evidence_page_num. Each block
carries the section it falls under (10-K/10-Q "Item N." headings) and the nearest
sub-heading, so chunks can be labelled with where they came from. Parsing problems
are returned as issue records rather than silently fixed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median

import pdfplumber

from finrag.ingest.layout import Line, group_lines
from finrag.ingest.tables import detect_tables
from finrag.ingest.text_repair import REPLACEMENT_CHAR, build_vocab, fix_glyphs, join_lines, repair_split_words

ITEM = re.compile(r"^(?:part\s+[iv]+\s*[,.\-—]?\s*)?item\s+(\d{1,2}[a-c]?)\b\.?", re.IGNORECASE)
NOTE = re.compile(r"^note\s+\d{1,2}\b", re.IGNORECASE)
PAGE_NUMBER = re.compile(r"^(?:page\s+)?(?:\d{1,3}|[ivxlc]{1,6})$", re.IGNORECASE)
# Statement captions such as "Years ended December 31" are headings but not sub-sections.
PERIOD_CAPTION = re.compile(r"^(?:\(?in\s+(?:millions|thousands|billions)|(?:for\s+the\s+)?(?:fiscal\s+)?"
                            r"(?:years?|three|six|nine|twelve|quarters?)\b)", re.IGNORECASE)
LOW_TEXT_CHARS = 200  # fewer characters than this on a page is worth flagging


@dataclass
class SectionState:
    section: str | None = None
    subsection: str | None = None


@dataclass
class ParsedPage:
    page_idx: int
    blocks: list[dict] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n\n".join(b["text"] for b in self.blocks)


def _issue(doc: str, page: int, kind: str, detail: str = "") -> dict:
    return {"doc_name": doc, "page_idx": page, "type": kind, "detail": detail}


def _is_heading(line: Line, body_size: float) -> bool:
    text = line.text.strip()
    if not re.search(r"[A-Za-z]{3}", text) or len(line.words) > 14:
        return False
    if ITEM.match(text) and len(line.words) <= 20:
        return True
    if text.endswith((".", ",", ";")) and not ITEM.match(text):
        return False
    return line.size >= body_size * 1.12 or line.bold


def _strip_boilerplate(lines: list[Line], height: float) -> list[Line]:
    """Drop the running 'Table of Contents' link and a page number on the last line."""
    kept = [line for line in lines
            if not (line.text.strip().lower() == "table of contents" and line.top < 0.12 * height)]
    if kept and PAGE_NUMBER.match(kept[-1].text.strip()) and kept[-1].top > 0.8 * height:
        kept.pop()
    return kept


def parse_pdf(pdf_path: Path, doc_name: str) -> tuple[list[ParsedPage], list[dict]]:
    issues: list[dict] = []
    raw: list[tuple[int, float, float, list[dict], int]] = []
    with pdfplumber.open(pdf_path) as pdf:
        for idx, page in enumerate(pdf.pages):
            words = page.extract_words(x_tolerance=3, y_tolerance=3, extra_attrs=["fontname", "size"])
            raw.append((idx, float(page.width), float(page.height), words, len(page.chars)))

    vocab = build_vocab([w["text"] for *_, words, _ in raw for w in words])
    state = SectionState()
    pages: list[ParsedPage] = []
    for idx, width, height, words, n_chars in raw:
        page = ParsedPage(idx)
        pages.append(page)
        if n_chars < LOW_TEXT_CHARS:
            issues.append(_issue(doc_name, idx, "low_text_page", f"{n_chars} chars (image-only or blank?)"))
        rotated = sum(1 for w in words if not w.get("upright", True))
        if rotated:
            issues.append(_issue(doc_name, idx, "rotated_text", f"{rotated} words not upright"))
        words = [w for w in words if w.get("upright", True)]
        if not words:
            continue
        cid = sum(w["text"].count("(cid:") for w in words)
        if cid:
            issues.append(_issue(doc_name, idx, "unmapped_cid_glyphs", f"{cid} (cid:N) sequences"))
        bad = sum(w["text"].count(REPLACEMENT_CHAR) for w in words)
        if bad:
            issues.append(_issue(doc_name, idx, "unmapped_glyph_u+fffd", f"{bad} characters"))

        repairs: list[str] = []
        lines = group_lines(words)
        for line in lines:
            line.words = repair_split_words(line.words, vocab, repairs)
        lines = _strip_boilerplate(lines, height)
        if not lines:
            continue
        body_size = median(w["size"] for line in lines for w in line.words)

        toc_page = sum(1 for line in lines if ITEM.match(line.text.strip())) >= 4
        if toc_page:
            issues.append(_issue(doc_name, idx, "table_of_contents_page", "section tracking skipped"))
        tables = {t.first: t for t in detect_tables(lines, width)}

        para: list[str] = []
        prev: Line | None = None

        def flush() -> None:
            if para:
                text = fix_glyphs(join_lines(para, vocab, repairs))
                page.blocks.append({"kind": "text", "text": text, **_where(state)})
                para.clear()

        i = 0
        while i < len(lines):
            if i in tables:
                flush()
                t = tables[i]
                page.blocks.append({"kind": "table", "text": t.markdown, "n_rows": t.n_rows,
                                    "n_cols": t.n_cols, **_where(state)})
                prev = lines[t.last]
                i = t.last + 1
                continue
            line = lines[i]
            if _is_heading(line, body_size):
                flush()
                text = fix_glyphs(line.text.strip())
                if not toc_page:
                    if ITEM.match(text):
                        state.section, state.subsection = text[:120], None
                    elif not PERIOD_CAPTION.match(text):
                        state.subsection = text[:120]
                page.blocks.append({"kind": "heading", "text": text, **_where(state)})
            else:
                if prev is not None and para and line.top - prev.bottom > 0.8 * max(prev.bottom - prev.top, 6.0):
                    flush()
                if NOTE.match(line.text.strip()) and not para and not toc_page:
                    state.subsection = fix_glyphs(line.text.strip())[:120]
                para.append(line.text)
            prev = line
            i += 1
        flush()
        for r in repairs:
            kind = "dehyphenated" if "- " in r.split(" -> ")[0] else "split_word_joined"
            issues.append(_issue(doc_name, idx, kind, r))
    return pages, issues


def _where(state: SectionState) -> dict:
    return {"section": state.section, "subsection": state.subsection}
