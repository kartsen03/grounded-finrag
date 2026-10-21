"""Embed both chunk sets through the gateway and load them into pgvector.

    python -m finrag.retrieval.index [--strategies fixed,structure]

Writes results/indexing/<strategy>.json with counts, timings and provenance.
"""

from __future__ import annotations

import argparse
import json
import time

import httpx
import numpy as np

from finrag import config, provenance
from finrag.gateway_client import GatewayClient
from finrag.retrieval.pipeline import EMBED_ALIAS
from finrag.retrieval.store import VectorStore

BATCH = 256  # texts per progress step; the client splits these into gateway calls of 64


def _model_server_device() -> str | None:
    try:
        return httpx.get("http://127.0.0.1:8090/health", timeout=5).json().get("device")
    except httpx.HTTPError:
        return None


def index_strategy(strategy: str, gateway: GatewayClient, store: VectorStore) -> dict:
    with (config.PROCESSED_DIR / f"chunks_{strategy}.jsonl").open(encoding="utf-8") as f:
        chunks = [json.loads(line) for line in f]
    t0 = time.perf_counter()
    parts = []
    for i in range(0, len(chunks), BATCH):
        parts.append(gateway.embed([c["embed_text"] for c in chunks[i:i + BATCH]], EMBED_ALIAS))
        if (i // BATCH) % 20 == 0:
            print(f"{strategy}: embedded {i + len(parts[-1])}/{len(chunks)}", flush=True)
    vectors = np.vstack(parts)
    embed_s = time.perf_counter() - t0

    t1 = time.perf_counter()
    store.reset(strategy, vectors.shape[1])
    store.insert(strategy, chunks, vectors)
    load_s = time.perf_counter() - t1
    t2 = time.perf_counter()
    store.create_indexes(strategy)
    index_s = time.perf_counter() - t2
    return {
        "strategy": strategy, "chunks": len(chunks), "rows_in_table": store.count(strategy),
        "dim": int(vectors.shape[1]), "embed_seconds": round(embed_s, 1),
        "chunks_per_second": round(len(chunks) / embed_s, 1), "load_seconds": round(load_s, 1),
        "hnsw_build_seconds": round(index_s, 1),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--strategies", default="fixed,structure")
    args = parser.parse_args(argv)
    gateway, store = GatewayClient(), VectorStore()
    out_dir = config.RESULTS_DIR / "indexing"
    out_dir.mkdir(parents=True, exist_ok=True)
    for strategy in args.strategies.split(","):
        stats = index_strategy(strategy, gateway, store)
        result = provenance.stamp("psycopg", "pgvector", step="indexing", embed_model=f"{config.EMBED_MODEL}@"
                                  f"{config.EMBED_MODEL_REVISION}", embed_device=_model_server_device(),
                                  path="rag-service -> llm-gateway -> model-server", **stats)
        (out_dir / f"{strategy}.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(json.dumps(stats))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
