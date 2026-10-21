"""Reciprocal Rank Fusion (Cormack, Clarke and Buettcher, 2009).

RRF(d) = sum over rankings r of 1 / (k + rank_r(d)), ranks starting at 1.
It uses ranks only, so BM25 scores (unbounded) and cosine similarities (in [-1, 1])
never need to be put on a common scale.
"""

from __future__ import annotations

RRF_K = 60


def rrf(rankings: list[list[str]], k: int = RRF_K) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    # Ties broken by ID so results are deterministic.
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
