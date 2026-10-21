"""Evidence-page retrieval metrics and bootstrap confidence intervals.

Retrieved chunks are turned into a ranked list of unique (document, page) pairs, using
each chunk's primary page (the page holding most of its text). A question is a hit@k
when any gold evidence page appears in the top k pages. MRR@10 is the mean reciprocal
rank of the first gold page within the top 10 (0 when absent).
Ranking pages rather than chunks makes the two chunking strategies comparable: a page
split into many small chunks cannot crowd the list, and a chunk is never credited for a
page it only touches with a few tokens.
"""

from __future__ import annotations

import random
from statistics import median

KS = (1, 3, 5, 10)


def ranked_pages(hits: list[dict]) -> list[tuple[str, int]]:
    seen: list[tuple[str, int]] = []
    for chunk in hits:
        key = (chunk["doc_name"], chunk["page_idx"])
        if key not in seen:
            seen.append(key)
    return seen


def first_gold_rank(pages: list[tuple[str, int]], gold: set[tuple[str, int]]) -> int | None:
    for rank, page in enumerate(pages, start=1):
        if page in gold:
            return rank
    return None


def question_metrics(rank: int | None) -> dict[str, float]:
    out = {f"hit@{k}": float(rank is not None and rank <= k) for k in KS}
    out["mrr@10"] = 1.0 / rank if rank is not None and rank <= 10 else 0.0
    return out


def aggregate(per_question: list[dict[str, float]]) -> dict[str, float]:
    keys = per_question[0].keys()
    return {k: round(sum(q[k] for q in per_question) / len(per_question), 4) for k in keys}


def bootstrap_ci(values: list[float], n: int = 2000, seed: int = 0, alpha: float = 0.05) -> tuple[float, float]:
    """Percentile bootstrap CI of the mean, resampling questions with replacement."""
    rng = random.Random(seed)
    means = sorted(sum(rng.choices(values, k=len(values))) / len(values) for _ in range(n))
    return round(means[int(alpha / 2 * n)], 4), round(means[int((1 - alpha / 2) * n) - 1], 4)


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return float("nan")
    pos = q * (len(ordered) - 1)
    lo, hi = int(pos), min(int(pos) + 1, len(ordered) - 1)
    return round(ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo), 2)


def latency_summary(timings: list[dict[str, float]]) -> dict[str, dict[str, float]]:
    stages = sorted({s for t in timings for s in t})
    return {s: {"p50": percentile([t[s] for t in timings if s in t], 0.5),
                "p95": percentile([t[s] for t in timings if s in t], 0.95)} for s in stages}


__all__ = ["KS", "ranked_pages", "first_gold_rank", "question_metrics", "aggregate", "bootstrap_ci",
           "latency_summary", "median"]
