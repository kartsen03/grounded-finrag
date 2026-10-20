"""Local model server: BGE embeddings and a cross-encoder re-ranker.

Only the LLM gateway calls this service (it binds to 127.0.0.1); the rag-service
reaches these models through the gateway's /v1/embeddings and /v1/rerank endpoints,
so every model call is authenticated, rate-limited, cached and audited in one place.

    MODEL_DEVICE=cuda uvicorn app:app --host 127.0.0.1 --port 8090

Environment:
    MODEL_DEVICE   cuda | cpu (default: cuda when available)
    EMBED_BATCH    batch size for embeddings (default 64)
    RERANK_BATCH   batch size for re-ranking pairs (default 32)
"""

from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager

import torch
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from sentence_transformers import CrossEncoder, SentenceTransformer

# Pinned Hugging Face revisions (commit SHAs); keep in sync with rag-service/src/finrag/config.py.
EMBED_MODELS = {"bge-base-en-v1.5": ("BAAI/bge-base-en-v1.5", "a5beb1e3e68b9ab74eb54cfd186867f64f240e1a")}
RERANK_MODELS = {"bge-reranker-base": ("BAAI/bge-reranker-base", "2cfc18c9415c912f9d8155881c133215df768a70")}
MAX_LENGTH = 512

DEVICE = os.environ.get("MODEL_DEVICE") or ("cuda" if torch.cuda.is_available() else "cpu")
EMBED_BATCH = int(os.environ.get("EMBED_BATCH", "64"))
RERANK_BATCH = int(os.environ.get("RERANK_BATCH", "32"))
models: dict[str, object] = {}


@asynccontextmanager
async def lifespan(_: FastAPI):
    dtype = torch.float16 if DEVICE == "cuda" else torch.float32
    for alias, (repo, rev) in EMBED_MODELS.items():
        m = SentenceTransformer(repo, revision=rev, device=DEVICE, model_kwargs={"torch_dtype": dtype})
        m.max_seq_length = MAX_LENGTH
        models[alias] = m
    for alias, (repo, rev) in RERANK_MODELS.items():
        models[alias] = CrossEncoder(repo, revision=rev, device=DEVICE, max_length=MAX_LENGTH,
                                     model_kwargs={"torch_dtype": dtype})
    yield
    models.clear()


app = FastAPI(title="finrag model server", version="0.1.0", lifespan=lifespan)


class EmbedRequest(BaseModel):
    model: str
    texts: list[str] = Field(min_length=1, max_length=512)
    normalize: bool = True


class EmbedResponse(BaseModel):
    model: str
    dim: int
    embeddings: list[list[float]]
    input_tokens: int
    device: str
    elapsed_ms: float


class RerankRequest(BaseModel):
    model: str
    query: str
    documents: list[str] = Field(min_length=1, max_length=512)


class RerankResponse(BaseModel):
    model: str
    scores: list[float]
    input_tokens: int
    device: str
    elapsed_ms: float


def _get(alias: str, kind: type):
    model = models.get(alias)
    if not isinstance(model, kind):
        raise HTTPException(status_code=404, detail=f"unknown model {alias!r}")
    return model


def _count_tokens(tokenizer, texts: list[str] | list[tuple[str, str]]) -> int:
    enc = tokenizer(texts, truncation=True, max_length=MAX_LENGTH) if isinstance(texts[0], str) else \
        tokenizer([a for a, _ in texts], [b for _, b in texts], truncation=True, max_length=MAX_LENGTH)
    return sum(len(ids) for ids in enc["input_ids"])


@app.get("/health")
def health() -> dict:
    return {"status": "ok" if models else "loading", "device": DEVICE, "models": sorted(models)}


@app.post("/embed", response_model=EmbedResponse)
def embed(req: EmbedRequest, x_request_id: str | None = Header(default=None)) -> EmbedResponse:
    model = _get(req.model, SentenceTransformer)
    t0 = time.perf_counter()
    vectors = model.encode(req.texts, batch_size=EMBED_BATCH, normalize_embeddings=req.normalize,
                           convert_to_numpy=True)
    elapsed = (time.perf_counter() - t0) * 1000
    return EmbedResponse(model=req.model, dim=int(vectors.shape[1]), embeddings=vectors.astype("float32").tolist(),
                         input_tokens=_count_tokens(model.tokenizer, req.texts), device=DEVICE,
                         elapsed_ms=round(elapsed, 2))


@app.post("/rerank", response_model=RerankResponse)
def rerank(req: RerankRequest, x_request_id: str | None = Header(default=None)) -> RerankResponse:
    model = _get(req.model, CrossEncoder)
    pairs = [(req.query, doc) for doc in req.documents]
    t0 = time.perf_counter()
    scores = model.predict(pairs, batch_size=RERANK_BATCH, convert_to_numpy=True)
    elapsed = (time.perf_counter() - t0) * 1000
    return RerankResponse(model=req.model, scores=[float(s) for s in scores],
                          input_tokens=_count_tokens(model.tokenizer, pairs), device=DEVICE,
                          elapsed_ms=round(elapsed, 2))
