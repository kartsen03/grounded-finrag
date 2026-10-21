"""rag-service HTTP API (FastAPI). Interactive OpenAPI docs at /docs.

    uvicorn finrag.api:app --host 127.0.0.1 --port 8000

Every request gets an X-Request-Id (the caller's, if it is safe, or a new one). The same ID
is sent to the LLM gateway on every model call made while serving the request.
"""

from __future__ import annotations

import re
import uuid
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Request
from pydantic import BaseModel, Field

from finrag.gateway_client import GatewayClient
from finrag.retrieval.pipeline import RetrievalConfig, Retriever
from finrag.retrieval.store import VectorStore

SAFE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
state: dict = {}


@asynccontextmanager
async def lifespan(_: FastAPI):
    state["retriever"] = Retriever(GatewayClient(), VectorStore())
    yield
    state.clear()


app = FastAPI(title="grounded-finrag rag-service", version="0.1.0", lifespan=lifespan,
              description="Retrieval and grounded answering over financial filings. Non-commercial (see NOTICE.md).")


@app.middleware("http")
async def request_id(request: Request, call_next):
    incoming = request.headers.get("X-Request-Id", "")
    rid = incoming if SAFE_ID.match(incoming) else uuid.uuid4().hex
    request.state.request_id = rid
    response = await call_next(request)
    response.headers["X-Request-Id"] = rid
    return response


class RetrieveRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    strategy: Literal["fixed", "structure"] = "structure"
    retriever: Literal["dense", "bm25", "hybrid"] = "hybrid"
    routing: bool = True
    rerank: bool = True
    top_k: int = Field(default=5, ge=1, le=50)


class RetrievedChunk(BaseModel):
    chunk_id: str
    doc_name: str
    page: int = Field(description="1-based PDF page number")
    section: str | None
    score: float
    text: str


class RetrieveResponse(BaseModel):
    request_id: str
    route: dict | None
    chunks: list[RetrievedChunk]
    timings_ms: dict[str, float]


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/retrieve", response_model=RetrieveResponse)
def retrieve(body: RetrieveRequest, request: Request) -> RetrieveResponse:
    cfg = RetrievalConfig(body.strategy, body.retriever, body.routing, body.rerank, top_k=body.top_k)
    rid = request.state.request_id
    res = state["retriever"].retrieve(body.question, cfg, request_id=rid)
    route = None
    if res.route is not None:
        route = {"companies": sorted(res.route.companies), "rule": res.route.rule,
                 "documents": sorted(res.route.doc_names) if res.route.doc_names else None}
    return RetrieveResponse(
        request_id=rid, route=route, timings_ms=res.timings_ms,
        chunks=[RetrievedChunk(chunk_id=h.chunk["chunk_id"], doc_name=h.chunk["doc_name"],
                               page=h.chunk["page_idx"] + 1, section=h.chunk["section"], score=h.score,
                               text=h.chunk["text"]) for h in res.hits])
