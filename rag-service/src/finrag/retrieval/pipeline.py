"""Retrieval pipeline: route -> dense and/or BM25 -> RRF -> cross-encoder re-rank.

Each stage is timed separately. Model calls (query embedding, re-ranking) go through
the gateway; BM25 runs in process over the same chunk text that was embedded.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from functools import lru_cache

import numpy as np

from finrag import config, corpus
from finrag.gateway_client import GatewayClient
from finrag.retrieval import routing
from finrag.retrieval.bm25 import BM25
from finrag.retrieval.fusion import rrf
from finrag.retrieval.store import VectorStore

EMBED_ALIAS = "bge-base-en-v1.5"
RERANK_ALIAS = "bge-reranker-base"
# Recommended query prefix for bge-*-en-v1.5 when matching short queries to passages.
QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


@dataclass(frozen=True)
class RetrievalConfig:
    strategy: str = "structure"  # fixed | structure
    retriever: str = "hybrid"  # dense | bm25 | hybrid
    routing: bool = True
    rerank: bool = True
    candidates: int = 50  # per retriever, and the size of the re-rank pool
    top_k: int = 10

    @property
    def label(self) -> str:
        return (f"{self.strategy}/{self.retriever}/{'routed' if self.routing else 'unrouted'}/"
                f"{'rerank' if self.rerank else 'norerank'}")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Hit:
    chunk: dict
    score: float


@dataclass
class RetrievalResult:
    hits: list[Hit]
    route: routing.Route | None
    timings_ms: dict[str, float] = field(default_factory=dict)


class ChunkIndex:
    """In-memory chunk table and BM25 index for one strategy."""

    def __init__(self, strategy: str):
        path = config.PROCESSED_DIR / f"chunks_{strategy}.jsonl"
        with path.open(encoding="utf-8") as f:
            self.chunks = [json.loads(line) for line in f]
        self.by_id = {c["chunk_id"]: c for c in self.chunks}
        self.doc_of = np.array([c["doc_name"] for c in self.chunks])
        self.bm25 = BM25([c["embed_text"] for c in self.chunks])

    def bm25_top(self, query: str, k: int, doc_names: frozenset[str] | None) -> list[tuple[str, float]]:
        scores = self.bm25.scores(query)
        if doc_names is not None:
            scores = np.where(np.isin(self.doc_of, list(doc_names)), scores, -np.inf)
        k = min(k, len(scores))
        top = np.argpartition(-scores, k - 1)[:k]
        ranked = sorted(top, key=lambda i: (-scores[i], self.chunks[i]["chunk_id"]))
        return [(self.chunks[i]["chunk_id"], float(scores[i])) for i in ranked if np.isfinite(scores[i])
                and scores[i] > 0]


@lru_cache(maxsize=2)
def chunk_index(strategy: str) -> ChunkIndex:
    return ChunkIndex(strategy)


class Retriever:
    def __init__(self, gateway: GatewayClient, store: VectorStore):
        self.gateway = gateway
        self.store = store
        self._docs: list | None = None

    @property
    def docs(self) -> list:
        # Loaded on first use: only routing needs the FinanceBench metadata (the CI gate runs without it).
        if self._docs is None:
            self._docs = corpus.corpus_docs()
        return self._docs

    def retrieve(self, question: str, cfg: RetrievalConfig, request_id: str | None = None) -> RetrievalResult:
        timings: dict[str, float] = {}
        start = time.perf_counter()

        def lap(name: str, t0: float) -> float:
            now = time.perf_counter()
            timings[name] = round((now - t0) * 1000, 2)
            return now

        idx = chunk_index(cfg.strategy)
        t = time.perf_counter()
        route = routing.route(question, self.docs) if cfg.routing else None
        allowed = route.doc_names if route else None
        t = lap("route", t)

        rankings: list[list[tuple[str, float]]] = []
        if cfg.retriever in ("dense", "hybrid"):
            qvec = self.gateway.embed([QUERY_INSTRUCTION + question], EMBED_ALIAS, request_id)[0]
            t = lap("embed_query", t)
            rankings.append(self.store.search(cfg.strategy, qvec, cfg.candidates, allowed))
            t = lap("dense_search", t)
        if cfg.retriever in ("bm25", "hybrid"):
            rankings.append(idx.bm25_top(question, cfg.candidates, allowed))
            t = lap("bm25", t)

        if len(rankings) == 2:
            fused = rrf([[cid for cid, _ in r] for r in rankings])
            t = lap("fusion", t)
        else:
            fused = rankings[0]
        pool = fused[:cfg.candidates]

        if cfg.rerank and pool:
            docs = [idx.by_id[cid]["embed_text"] for cid, _ in pool]
            scores = self.gateway.rerank(question, docs, RERANK_ALIAS, request_id)
            pool = sorted(zip([cid for cid, _ in pool], scores), key=lambda r: (-r[1], r[0]))
            t = lap("rerank", t)

        hits = [Hit(idx.by_id[cid], float(score)) for cid, score in pool[:cfg.top_k]]
        timings["total"] = round((time.perf_counter() - start) * 1000, 2)
        return RetrievalResult(hits, route, timings)
