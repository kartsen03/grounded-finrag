"""Check FinanceBench's gold evidence pages against our parsed pages.

For every evidence item, compare the evidence text's words with the words of parsed
pages p-1, p and p+1 (p = evidence_page_num). If p is the best match, the page index
convention (0-based) and our page text are consistent with the gold label. Evidence
whose words are poorly covered by every nearby page points at a parsing problem (or
a label problem), and is listed for the error analysis.
"""

from __future__ import annotations

import re

_WORD = re.compile(r"[a-z0-9]{3,}")
MIN_COVERAGE = 0.6


def _words(text: str) -> set[str]:
    return set(_WORD.findall(text.lower().replace(",", "")))


def check(questions: dict[str, dict], page_text: dict[tuple[str, int], str]) -> dict:
    outcomes = {"best_is_p": 0, "best_is_p_minus_1": 0, "best_is_p_plus_1": 0, "weak_coverage": 0}
    weak: list[dict] = []
    coverages: list[float] = []
    for qid, q in sorted(questions.items()):
        for ev in q["evidence"]:
            p = int(ev["evidence_page_num"])
            target = _words(ev["evidence_text"])
            if not target:
                continue
            cov = {}
            for cand in (p - 1, p, p + 1):
                text = page_text.get((ev["doc_name"], cand))
                if text is not None:
                    cov[cand] = len(target & _words(text)) / len(target)
            best = max(cov, key=lambda c: (cov[c], c == p)) if cov else None
            best_cov = cov.get(best, 0.0) if best is not None else 0.0
            coverages.append(cov.get(p, 0.0))
            if best_cov < MIN_COVERAGE:
                outcomes["weak_coverage"] += 1
                weak.append({"financebench_id": qid, "doc_name": ev["doc_name"], "evidence_page_num": p,
                             "coverage_at_p": round(cov.get(p, 0.0), 3)})
            elif best == p:
                outcomes["best_is_p"] += 1
            elif best == p - 1:
                outcomes["best_is_p_minus_1"] += 1
            else:
                outcomes["best_is_p_plus_1"] += 1
    coverages.sort()
    return {
        "evidence_items": sum(outcomes.values()),
        "outcomes": outcomes,
        "min_coverage": MIN_COVERAGE,
        "median_coverage_at_p": coverages[len(coverages) // 2] if coverages else None,
        "weak_items": weak,
    }
