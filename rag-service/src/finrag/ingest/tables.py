"""Recover tables from aligned text and render them as Markdown.

Detection works on lines (see layout.py):
  1. A line is a *row* when it ends in a run of numeric cells set apart from its
     label: two or more numbers, or one number after a wide gap.
  2. Rows (plus short label-only lines between them, such as "Net revenue:") form a
     table block when the block holds at least two rows.
  3. Columns are clusters of the numeric cells' right edges, because numbers in
     financial statements are right-aligned.
  4. Header lines directly above the block (years, "December 31,", "(In millions)")
     are attached to the columns they overlap.
"""

from __future__ import annotations

from dataclasses import dataclass

from finrag.ingest.layout import DASH, YEAR, Cell, Line, split_cells

COLUMN_GAP = 12.0  # min gap (pt) between a label and a lone number for the line to count as a row
COLUMN_TOL = 10.0  # right edges closer than this (pt) belong to the same column
MAX_BRIDGE = 2  # label-only lines allowed between two rows inside one block
MAX_HEADER_LINES = 4


@dataclass
class TableBlock:
    first: int  # index of first line (including header lines)
    last: int  # index of last line, inclusive
    markdown: str
    n_rows: int
    n_cols: int


def _trailing_numbers(cells: list[Cell]) -> int:
    n = 0
    for cell in reversed(cells):
        if not cell.numeric:
            break
        n += 1
    return n


def _is_year_row(cells: list[Cell]) -> bool:
    n = _trailing_numbers(cells)
    label_words = sum(len(c.text.split()) for c in cells[: len(cells) - n])
    return n >= 1 and all(YEAR.match(c.value) for c in cells[len(cells) - n:]) and label_words <= 4


def classify(line: Line) -> tuple[str, list[Cell]]:
    """'row' (label + numbers), 'label' (short text, no numbers) or 'other'."""
    cells = split_cells(line)
    n_num = _trailing_numbers(cells)
    if n_num >= 2:
        return "row", cells
    if n_num == 1 and len(cells) >= 2 and cells[-1].x0 - cells[-2].x1 >= COLUMN_GAP:
        return "row", cells
    if n_num == 0 and len(line.words) <= 12 and not line.text.rstrip().endswith("."):
        return "label", cells
    return "other", cells


def _close(prev: Line, nxt: Line) -> bool:
    return nxt.top - prev.bottom <= 2.5 * max(prev.bottom - prev.top, 6.0)


def find_blocks(kinds: list[str], lines: list[Line]) -> list[tuple[int, int]]:
    """Index ranges [start, end] of row runs, bridging short label-only stretches."""
    blocks: list[tuple[int, int]] = []
    i, n = 0, len(lines)
    while i < n:
        if kinds[i] != "row":
            i += 1
            continue
        start = end = i
        j = i + 1
        while j < n:
            if kinds[j] == "row" and _close(lines[end], lines[j]):
                end = j
                j += 1
                continue
            # Bridge label lines (section rows, wrapped labels) if a row follows soon.
            k = j
            while k < n and k - end <= MAX_BRIDGE and kinds[k] == "label" and _close(lines[k - 1], lines[k]):
                k += 1
            if k < n and k > j and kinds[k] == "row" and k - end <= MAX_BRIDGE + 1 and _close(lines[k - 1], lines[k]):
                end = k
                j = k + 1
                continue
            break
        rows = [t for t in range(start, end + 1) if kinds[t] == "row"]
        if len(rows) >= 2 and rows[-1] > rows[0]:
            blocks.append((start, end))
        i = end + 1
    return blocks


def _columns(numeric_cells: list[Cell]) -> list[tuple[float, float, float]]:
    """Union of overlapping numeric-cell spans -> list of (center, span_x0, span_x1), left to right.

    Spans rather than edges, because alignment varies: numbers are usually right-aligned,
    but dashes are often centered and some filings left-align.
    """
    spans: list[list[float]] = []
    for cell in sorted(numeric_cells, key=lambda c: c.x0):
        if spans and cell.x0 <= spans[-1][1] + COLUMN_TOL / 5:
            spans[-1][1] = max(spans[-1][1], cell.x1)
        else:
            spans.append([cell.x0, cell.x1])
    return [((x0 + x1) / 2, x0, x1) for x0, x1 in spans]


def _nearest(columns: list[tuple[float, float, float]], cell: Cell) -> int:
    """Column overlapping the cell the most; nearest center when none overlaps."""
    def score(k: int) -> tuple[float, float]:
        _, x0, x1 = columns[k]
        overlap = min(x1, cell.x1) - max(x0, cell.x0)
        return (max(overlap, 0.0), -abs(columns[k][0] - (cell.x0 + cell.x1) / 2))
    return max(range(len(columns)), key=score)


def _md(text: str) -> str:
    return text.replace("|", "\\|").strip()


def _clean_value(cell: Cell) -> str:
    v = cell.value
    return "—" if DASH.match(v) else v


def build_table(lines: list[Line], cells: list[list[Cell]], kinds: list[str], start: int, end: int,
                page_width: float, floor: int = 0) -> TableBlock:
    # Leading rows whose numbers are all years ("(Millions)  2018  2017  2016") are column
    # headers. Years are often centered rather than right-aligned, so they must not take
    # part in column clustering.
    header_rows: list[list[Cell]] = []
    body_start = start
    while body_start < end and kinds[body_start] == "row" and _is_year_row(cells[body_start]):
        header_rows.append(cells[body_start])
        body_start += 1
    rows_idx = [t for t in range(body_start, end + 1) if kinds[t] == "row"]
    numeric = [c for t in rows_idx for c in cells[t][len(cells[t]) - _trailing_numbers(cells[t]):]]
    columns = _columns(numeric)
    numeric_left = columns[0][1] - 4.0

    # Header lines directly above the block.
    first = start
    above: list[list[Cell]] = []
    t = start - 1
    while t >= floor and len(above) < MAX_HEADER_LINES and kinds[t] in ("label", "row") and _close(lines[t], lines[t + 1]):
        line_cells = cells[t]
        if not any(c.x1 > numeric_left for c in line_cells):
            break
        if any(c.x1 - c.x0 > 0.45 * page_width for c in line_cells):
            break
        above.insert(0, line_cells)
        first = t
        t -= 1
    header_rows = above + header_rows

    n_cols = len(columns)
    stub_parts: list[str] = []
    col_heads: list[list[str]] = [[] for _ in range(n_cols)]
    for hrow in header_rows:
        for cell in hrow:
            if cell.x1 <= numeric_left:
                stub_parts.append(cell.text)
                continue
            hits = [k for k, (_, x0, x1) in enumerate(columns) if cell.x0 <= x1 + 6 and cell.x1 >= x0 - 6]
            for k in hits or [_nearest(columns, cell)]:
                col_heads[k].append(cell.text)

    body: list[list[str]] = []
    pending_label = ""
    for t in range(body_start, end + 1):
        row_cells = cells[t]
        if kinds[t] == "label":
            text = " ".join(c.text for c in row_cells)
            if pending_label and text[:1].islower():
                pending_label = f"{pending_label} {text}"  # wrapped label continues
                continue
            if pending_label:
                body.append([pending_label] + [""] * n_cols)
            pending_label = text
            continue
        n_num = _trailing_numbers(row_cells)
        label = " ".join(c.text for c in row_cells[: len(row_cells) - n_num])
        if pending_label:
            # A label line followed by a row whose label continues it in lowercase is one wrapped label.
            if label[:1].islower() or label[:1] in "$(" or not label:
                label = f"{pending_label} {label}".strip()
            else:
                body.append([pending_label] + [""] * n_cols)
            pending_label = ""
        values = [""] * n_cols
        for cell in row_cells[len(row_cells) - n_num:]:
            k = _nearest(columns, cell)
            values[k] = f"{values[k]} {_clean_value(cell)}".strip()
        body.append([label] + values)
    if pending_label:
        body.append([pending_label] + [""] * n_cols)

    header = [" ".join(stub_parts)] + [" ".join(h) for h in col_heads]
    md_lines = ["| " + " | ".join(_md(h) for h in header) + " |",
                "|" + "---|" * (n_cols + 1)]
    md_lines += ["| " + " | ".join(_md(v) for v in row) + " |" for row in body]
    return TableBlock(first=first, last=end, markdown="\n".join(md_lines), n_rows=len(body), n_cols=n_cols)


def detect_tables(lines: list[Line], page_width: float) -> list[TableBlock]:
    classified = [classify(line) for line in lines]
    kinds = [k for k, _ in classified]
    cells = [c for _, c in classified]
    tables: list[TableBlock] = []
    floor = 0  # header scanning must not reach back into the previous table
    for s, e in find_blocks(kinds, lines):
        tables.append(build_table(lines, cells, kinds, s, e, page_width, floor))
        floor = e + 1
    return tables
