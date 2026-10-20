"""Build synthetic pdfplumber-style words so parsing logic can be tested without PDFs."""

from __future__ import annotations

CHAR_W = 4.5  # approximate glyph width at 9pt


def word(text: str, x0: float, top: float, size: float = 9.0, bold: bool = False) -> dict:
    return {
        "text": text, "x0": x0, "x1": x0 + CHAR_W * len(text), "top": top, "bottom": top + size,
        "size": size, "fontname": "Arial-BoldMT" if bold else "ArialMT", "upright": True,
    }


def line_words(top: float, *cells: tuple[float, str], size: float = 9.0) -> list[dict]:
    """Each cell is (x0, "space separated words"); words inside a cell are 2pt apart."""
    out = []
    for x0, text in cells:
        x = x0
        for token in text.split():
            w = word(token, x, top, size)
            out.append(w)
            x = w["x1"] + 2.0
    return out
