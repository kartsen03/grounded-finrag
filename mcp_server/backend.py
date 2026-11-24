"""Backend used by the MCP tools: the existing grounded-finrag pipeline, unchanged.

search_filings and answer_question call the LLM gateway (query embeddings, re-ranking, chat) with
this server's own API key, so authentication, rate limiting and the audit log apply to every model
call. list_filings reads the indexed chunk table in PostgreSQL. Nothing here writes anything.

Configuration comes only from the environment:
    GATEWAY_API_KEY     required; the gateway key for this client (never logged or returned)
    GATEWAY_URL         default http://127.0.0.1:8080
    FINRAG_PG_DSN       default: the local docker-compose database
"""

from __future__ import annotations

import os
import threading
import uuid
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import quote

from finrag.retrieval.store import DEFAULT_DSN

GATEWAY_TIMEOUT_S = 150.0  # per HTTP call; a cold 7B model load plus generation can take over a minute
DB_CONNECT_TIMEOUT_S = 5
DB_STATEMENT_TIMEOUT_MS = 15_000


class Backend(Protocol):
    def list_filings(self) -> list[dict]: ...

    def search(self, query: str, doc_names: frozenset[str] | None, k: int, request_id: str) -> list[dict]: ...

    def answer(self, question: str, company: str | None, request_id: str) -> dict: ...


def new_request_id() -> str:
    return f"mcp-{uuid.uuid4().hex}"


def _dsn_with_timeouts(dsn: str) -> str:
    sep = "&" if "?" in dsn else "?"
    options = quote(f"-c statement_timeout={DB_STATEMENT_TIMEOUT_MS}")
    return f"{dsn}{sep}connect_timeout={DB_CONNECT_TIMEOUT_S}&options={options}"


@dataclass
class FinragBackend:
    """Lazily builds the retriever and answerer on first use (the BM25 index takes a while)."""

    api_key: str
    gateway_url: str
    dsn: str

    def __post_init__(self) -> None:
        self._lock = threading.Lock()  # one psycopg connection and one in-memory index: serialize calls
        self._parts = None

    @classmethod
    def from_env(cls) -> "FinragBackend":
        key = os.environ.get("GATEWAY_API_KEY", "").strip()
        if not key:
            raise RuntimeError("GATEWAY_API_KEY is not set; the MCP server needs its own gateway API key")
        return cls(api_key=key, gateway_url=os.environ.get("GATEWAY_URL", "http://127.0.0.1:8080"),
                   dsn=os.environ.get("FINRAG_PG_DSN", DEFAULT_DSN))

    def _build(self):
        if self._parts is None:
            from finrag.answer.pipeline import Answerer
            from finrag.api import final_answer_config
            from finrag.gateway_client import GatewayClient
            from finrag.retrieval.pipeline import Retriever, chunk_index
            from finrag.retrieval.store import VectorStore

            gateway = GatewayClient(base_url=self.gateway_url, api_key=self.api_key, timeout=GATEWAY_TIMEOUT_S)
            retriever = Retriever(gateway, VectorStore(_dsn_with_timeouts(self.dsn)))
            cfg = final_answer_config()  # selected retrieval config + dev-tuned abstention threshold
            chunk_index(cfg.retrieval.strategy)  # build BM25 once
            self._parts = (retriever, Answerer(gateway, retriever), cfg)
        return self._parts

    def warm_up(self) -> None:
        with self._lock:
            self._build()

    def list_filings(self) -> list[dict]:
        with self._lock:
            retriever, _, cfg = self._build()
            table = {"fixed": "chunks_fixed", "structure": "chunks_structure"}[cfg.retrieval.strategy]
            with retriever.store.conn.cursor() as cur:
                cur.execute(f"SELECT doc_name, company, doc_type, fiscal_year, fiscal_quarter, count(*) "
                            f"FROM {table} GROUP BY 1, 2, 3, 4, 5 ORDER BY company, fiscal_year, doc_name")
                rows = cur.fetchall()
        return [{"doc_name": d, "company": c, "doc_type": t, "fiscal_year": y, "fiscal_quarter": q, "chunks": n}
                for d, c, t, y, q, n in rows]

    def search(self, query: str, doc_names: frozenset[str] | None, k: int, request_id: str) -> list[dict]:
        from finrag.retrieval.pipeline import RetrievalConfig

        with self._lock:
            retriever, _, cfg = self._build()
            rcfg = RetrievalConfig(**{**cfg.retrieval.to_dict(), "top_k": k})
            res = retriever.retrieve(query, rcfg, request_id=request_id, doc_names=doc_names)
        return [{"doc_name": h.chunk["doc_name"], "page": h.chunk["page_idx"] + 1, "section": h.chunk["section"],
                 "score": h.score, "text": h.chunk["text"]} for h in res.hits]

    def answer(self, question: str, company: str | None, request_id: str) -> dict:
        from finrag.retrieval import routing

        with self._lock:
            retriever, answerer, cfg = self._build()
            doc_names = None
            if company is not None:
                # The evaluated routing (fiscal year/quarter fallback chain), restricted to the named company.
                docs = [d for d in retriever.docs if d.company == company]
                doc_names = routing.route(f"{company}: {question}", docs).doc_names
            return answerer.answer(question, cfg, request_id=request_id, doc_names=doc_names)
