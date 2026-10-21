"""CI retrieval regression gate on a small synthetic fixture corpus (CPU, no FinanceBench data).

    python -m finrag.ci.retrieval_gate                    # fail (exit 1) if hit@5 drops below baseline
    python -m finrag.ci.retrieval_gate --update-baseline  # record a new baseline (reviewed in the PR diff)

Runs the real path: structure chunking -> embeddings through the gateway (model server on CPU)
-> pgvector table chunks_ci + BM25 -> RRF, then scores evidence-page hit@k on the fixture
questions. The baseline lives in results/ci/retrieval_gate_baseline.json.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from finrag import config, provenance
from finrag.corpus import DocMeta
from finrag.eval import metrics
from finrag.gateway_client import GatewayClient
from finrag.ingest.chunking import structure_chunks
from finrag.retrieval import pipeline
from finrag.retrieval.pipeline import EMBED_ALIAS, RetrievalConfig, Retriever
from finrag.retrieval.store import VectorStore

FIXTURE = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "ci_corpus" / "pages.json"
BASELINE = config.RESULTS_DIR / "ci" / "retrieval_gate_baseline.json"
GATE_CONFIG = RetrievalConfig("ci", "hybrid", routing=False, rerank=False, top_k=10)


def run() -> dict:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    chunks = []
    for doc in data["documents"]:
        meta = DocMeta(doc["doc_name"], doc["company"], doc["doc_type"], doc["fiscal_year"],
                       doc.get("fiscal_quarter"), None, "fixture")
        chunks += [c.to_dict() for c in structure_chunks(meta, doc["pages"])]
    tmp = Path(tempfile.mkdtemp(prefix="finrag-ci-"))
    with (tmp / "chunks_ci.jsonl").open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c) + "\n")
    config.PROCESSED_DIR = tmp  # ChunkIndex reads chunks_<strategy>.jsonl from here
    pipeline.chunk_index.cache_clear()

    gateway, store = GatewayClient(), VectorStore()
    vectors = gateway.embed([c["embed_text"] for c in chunks], EMBED_ALIAS, request_id="ci-gate-index")
    store.reset("ci", vectors.shape[1])
    store.insert("ci", chunks, vectors)
    store.create_indexes("ci")

    retriever = Retriever(gateway, store)
    per_q = []
    for q in data["questions"]:
        res = retriever.retrieve(q["question"], GATE_CONFIG, request_id=f"ci-gate-{q['id']}")
        rank = metrics.first_gold_rank(metrics.ranked_pages([h.chunk for h in res.hits]),
                                       {(d, p) for d, p in q["gold"]})
        per_q.append(metrics.question_metrics(rank))
    return {"questions": len(per_q), "chunks": len(chunks), "metrics": metrics.aggregate(per_q),
            "config": GATE_CONFIG.to_dict()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args(argv)
    result = run()
    print(json.dumps(result["metrics"]))
    if args.update_baseline:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps({**provenance.stamp(step="ci_retrieval_gate_baseline"), **result}, indent=2)
                            + "\n", encoding="utf-8", newline="\n")
        print(f"baseline written: {BASELINE}")
        return 0
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))["metrics"]
    if result["metrics"]["hit@5"] < baseline["hit@5"]:
        print(f"FAIL: hit@5 {result['metrics']['hit@5']} < baseline {baseline['hit@5']}", file=sys.stderr)
        return 1
    print(f"PASS: hit@5 {result['metrics']['hit@5']} >= baseline {baseline['hit@5']} "
          f"(mrr@10 {result['metrics']['mrr@10']}, baseline {baseline['mrr@10']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
