"""Words -> lines -> cells. The geometry every later parsing step relies on.

pdfplumber gives positioned words (x0, x1, top, bottom, size, fontname). Financial
statements have no reliable ruling lines, so tables are recovered from alignment:
a line is split into "cells" wherever the horizontal gap between words is wider
than a normal space.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from statistics import median

_BOLD = re.compile(r"bold|black|heavy|semibold|demi", re.IGNORECASE)
# A number as printed in filings: 1,577  (1,577)  -3.2  5.5%  (0.4)%  2018
NUMBER = re.compile(r"^\(?-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?\)?%?$")
# Placeholders for nil values. U+FFFD shows up when a dash glyph has no Unicode mapping.
DASH = re.compile(r"^[—–\-−�]+$")
YEAR = re.compile(r"^(19|20)\d{2}$")


@dataclass
class Line:
    words: list[dict] = field(default_factory=list)

    @property
    def top(self) -> float:
        return min(w["top"] for w in self.words)

    @property
    def bottom(self) -> float:
        return max(w["bottom"] for w in self.words)

    @property
    def x0(self) -> float:
        return self.words[0]["x0"]

    @property
    def x1(self) -> float:
        return max(w["x1"] for w in self.words)

    @property
    def size(self) -> float:
        return median(w["size"] for w in self.words)

    @property
    def bold(self) -> bool:
        return all(_BOLD.search(w.get("fontname", "")) for w in self.words)

    @property
    def text(self) -> str:
        return " ".join(w["text"] for w in self.words)


@dataclass
class Cell:
    text: str
    x0: float
    x1: float

    @property
    def value(self) -> str:
        """Cell text without currency signs or inner spaces: '$ 5,363' -> '5,363'."""
        return self.text.replace("$", "").replace(" ", "")

    @property
    def numeric(self) -> bool:
        v = self.value
        return bool(v) and (bool(NUMBER.match(v)) or bool(DASH.match(v)))


def group_lines(words: list[dict], y_tol: float = 3.0) -> list[Line]:
    """Cluster words into visual lines by vertical center, then order each line left to right."""
    lines: list[Line] = []
    centers: list[float] = []
    for w in sorted(words, key=lambda w: ((w["top"] + w["bottom"]) / 2, w["x0"])):
        cy = (w["top"] + w["bottom"]) / 2
        if lines and abs(cy - centers[-1]) <= y_tol:
            lines[-1].words.append(w)
        else:
            lines.append(Line([w]))
            centers.append(cy)
    for line in lines:
        line.words.sort(key=lambda w: w["x0"])
    return lines


def split_cells(line: Line, gap: float | None = None) -> list[Cell]:
    """Split a line into cells at gaps wider than a space. A lone '$' joins the next word."""
    if gap is None:
        gap = max(4.0, 0.6 * line.size)
    cells: list[Cell] = []
    current: list[dict] = []
    for w in line.words:
        if current and w["x0"] - current[-1]["x1"] > gap and current[-1]["text"] != "$":
            cells.append(_cell(current))
            current = []
        current.append(w)
    if current:
        cells.append(_cell(current))
    return cells


def _cell(words: list[dict]) -> Cell:
    return Cell(" ".join(w["text"] for w in words), words[0]["x0"], max(w["x1"] for w in words))
