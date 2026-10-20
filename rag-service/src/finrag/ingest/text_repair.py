"""Repairs for common PDF text-extraction defects. Every repair is logged as an issue.

- Split words: kerning gaps make pdfplumber emit "Flow s" for "Flows". Two adjacent
  words are joined when one of them is a fragment and the joined form occurs elsewhere
  in the same document.
- Hyphenation: "reve-" at a line end + "nue" on the next line becomes "revenue" when
  "revenue" occurs elsewhere in the document; otherwise the hyphen is kept ("long-term").
- Unmapped glyphs: dashes and apostrophes without a Unicode mapping arrive as U+FFFD.
"""

from __future__ import annotations

import re
from collections import Counter

_ALPHA = re.compile(r"^[A-Za-z]+$")
_SINGLE_LETTER_WORDS = {"a", "i"}
REPLACEMENT_CHAR = "�"


def build_vocab(words: list[str]) -> Counter:
    return Counter(w.lower() for w in words if _ALPHA.match(w))


def _is_fragment(token: str, vocab: Counter) -> bool:
    low = token.lower()
    if len(low) == 1:
        return low not in _SINGLE_LETTER_WORDS
    return len(low) <= 3 and vocab[low] <= 2


def repair_split_words(words: list[dict], vocab: Counter, log: list[str]) -> list[dict]:
    """Join kerning-split fragments within one line. Appends "a b -> ab" strings to log."""
    out: list[dict] = []
    for w in words:
        if out:
            prev = out[-1]
            a, b = prev["text"], w["text"]
            gap = w["x0"] - prev["x1"]
            joined = a + b
            if (_ALPHA.match(a) and _ALPHA.match(b) and gap < 0.5 * w["size"]
                    and (_is_fragment(a, vocab) or _is_fragment(b, vocab))
                    and vocab[joined.lower()] >= 2):
                out[-1] = {**prev, "text": joined, "x1": w["x1"]}
                log.append(f"{a} {b} -> {joined} (gap {gap:.1f}pt)")
                continue
        out.append(w)
    return out


def join_lines(lines: list[str], vocab: Counter, log: list[str]) -> str:
    """Join the lines of one paragraph, undoing end-of-line hyphenation where safe."""
    text = ""
    for line in lines:
        line = line.strip()
        if not text:
            text = line
            continue
        m = re.search(r"([A-Za-z]+)-$", text)
        first = re.match(r"[a-z]+", line)
        if m and first:
            candidate = (m.group(1) + first.group(0)).lower()
            if vocab[candidate] >= 1:
                log.append(f"{m.group(1)}- {first.group(0)} -> {m.group(1)}{first.group(0)}")
                text = text[:-1] + line
                continue
            text = text + line  # keep the hyphen: compound split at a line end
            continue
        text = f"{text} {line}"
    return text


def fix_glyphs(text: str) -> str:
    """U+FFFD attached to a preceding letter is an apostrophe ("company's", "plans' "); a
    free-standing one is a dash ("Note 4 - Segment Reporting", "Other - net")."""
    text = re.sub(rf"(?<=[A-Za-z]){REPLACEMENT_CHAR}(?=[A-Za-z\s]|$)", "’", text)
    return text.replace(REPLACEMENT_CHAR, "—")
