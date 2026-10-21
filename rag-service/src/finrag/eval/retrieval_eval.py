"""Retrieval ablation: every chunking x retriever x routing x re-ranking combination.

    python -m finrag.eval.retrieval_eval --split dev            # all 24 configurations
    python -m finrag.eval.retrieval_eval --split test           # selected configs only, once

Dev writes results/retrieval/dev_ablation.json (+ per-question ranks) and records the
configuration chosen by SELECTION_RULE in results/retrieval/selected.json. Test refuses
to run any configuration that is not in selected.json, and refuses to overwrite an
existing test result: the test set is scored once per final configuration.
"""

from __future__ import annotations

import argparse
import itertools
import json
import random

from finrag import config, corpus, provenance
from finrag.eval import metrics
from finrag.gateway_client import GatewayClient
from finrag.retrieval.pipeline import EMBED_ALIAS, QUERY_INSTRUCTION, RetrievalConfig, Retriever, chunk_index
from finrag.retrieval.store import VectorStore

OUT = config.RESULTS_DIR / "retrieval"
TOP_K_CHUNKS = 20  # enough chunks to rank 10 unique pages
WARMUP_QUESTIONS = 5
# Fixed before the first dev run: maximize MRR@10, then hit@5, then minimize p50 total latency.
SELECTION_RULE = "max mrr@10, then max hit@5, then min p50 total latency (dev split)"
NAIVE = RetrievalConfig("fixed", "dense", routing=False, rerank=False, top_k=TOP_K_CHUNKS)


def all_configs() -> list[RetrievalConfig]:
    return [RetrievalConfig(s, r, routing=ro, rerank=re, top_k=TOP_K_CHUNKS)
            for s, r, ro, re in itertools.product(("fixed", "structure"), ("dense", "bm25", "hybrid"),
                                                  (False, True), (False, True))]


def evaluate(retriever: Retriever, cfg: RetrievalConfig, qids: list[str]) -> dict:
    per_q, timings, routed_ok, routed_n = [], [], 0, 0
    for qid in qids:
        q = corpus.questions()[qid]
        res = retriever.retrieve(q["question"], cfg, request_id=f"eval-{qid}")
        pages = metrics.ranked_pages([h.chunk for h in res.hits])
        gold = corpus.evidence_pages(q)
        rank = metrics.first_gold_rank(pages, gold)
        m = metrics.question_metrics(rank)
        per_q.append({"financebench_id": qid, "question_type": q["question_type"], "gold_rank": rank,
                      "top_pages": [f"{d}:{p}" for d, p in pages[:10]], **m,
                      "route_rule": res.route.rule if res.route else None})
        timings.append(res.timings_ms)
        if res.route is not None and res.route.doc_names is not None:
            routed_n += 1
            routed_ok += q["doc_name"] in res.route.doc_names
    summary = metrics.aggregate([{k: q[k] for k in q if k.startswith(("hit@", "mrr@"))} for q in per_q])
    ci = {k: metrics.bootstrap_ci([q[k] for q in per_q]) for k in ("hit@5", "mrr@10")}
    by_type = {t: metrics.aggregate([{k: q[k] for k in ("hit@5", "mrr@10")} for q in per_q if q["question_type"] == t])
               for t in sorted({q["question_type"] for q in per_q})}
    return {"config": cfg.to_dict(), "label": cfg.label, "n": len(qids), "metrics": summary, "ci95": ci,
            "by_question_type": by_type, "latency_ms": metrics.latency_summary(timings),
            "routing": {"filtered": routed_n, "gold_doc_in_filter": routed_ok} if cfg.routing else None,
            "per_question": per_q}


def hnsw_recall(retriever: Retriever, qids: list[str], k: int = 50) -> dict:
    """Overlap of HNSW and exact top-k for unfiltered dense search (index quality check)."""
    out = {}
    for strategy in ("fixed", "structure"):
        overlaps = []
        for qid in qids:
            qvec = retriever.gateway.embed([QUERY_INSTRUCTION + corpus.questions()[qid]["question"]], EMBED_ALIAS)[0]
            approx = {c for c, _ in retriever.store.search(strategy, qvec, k)}
            exact = {c for c, _ in retriever.store.search(strategy, qvec, k, exact=True)}
            overlaps.append(len(approx & exact) / k)
        out[strategy] = round(sum(overlaps) / len(overlaps), 4)
    return {f"recall@{k}": out}


def select(results: list[dict]) -> dict:
    return max(results, key=lambda r: (r["metrics"]["mrr@10"], r["metrics"]["hit@5"],
                                       -r["latency_ms"]["total"]["p50"]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--split", choices=("dev", "test"), required=True)
    args = parser.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    qids = corpus.split()[args.split]
    retriever = Retriever(GatewayClient(), VectorStore())
    for strategy in ("fixed", "structure"):
        chunk_index(strategy)  # build BM25 before timing anything

    if args.split == "dev":
        configs = all_configs()
    else:
        selected = json.loads((OUT / "selected.json").read_text(encoding="utf-8"))
        configs = [RetrievalConfig(**c) for c in selected["test_configs"]]
        target = OUT / "test_results.json"
        if target.exists():
            raise SystemExit(f"{target} exists: the test split has already been scored for these configs")

    # Warm up GPU clocks, model caches and DB connections on questions that are not timed.
    warm = random.Random(0).sample(corpus.split()["dev"], WARMUP_QUESTIONS)
    for cfg in configs:
        evaluate(retriever, cfg, warm)

    results = []
    for cfg in configs:
        r = evaluate(retriever, cfg, qids)
        results.append(r)
        print(f"{cfg.label:40s} " + " ".join(f"{k}={v:.3f}" for k, v in r["metrics"].items())
              + f"  p50={r['latency_ms']['total']['p50']}ms", flush=True)

    stamp = provenance.stamp("psycopg", "pgvector", "numpy", "scipy", step=f"retrieval_eval_{args.split}",
                             split=args.split, n_questions=len(qids), top_k_chunks=TOP_K_CHUNKS,
                             embed_model=f"{config.EMBED_MODEL}@{config.EMBED_MODEL_REVISION}",
                             rerank_model=f"{config.RERANK_MODEL}@{config.RERANK_MODEL_REVISION}")
    per_question = {r["label"]: r.pop("per_question") for r in results}
    if args.split == "dev":
        best = select(results)
        payload = {**stamp, "selection_rule": SELECTION_RULE, "selected": best["label"],
                   "hnsw": hnsw_recall(retriever, qids), "results": results}
        (OUT / "dev_ablation.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")
        (OUT / "dev_per_question.json").write_text(json.dumps(per_question, indent=1) + "\n", encoding="utf-8",
                                                   newline="\n")
        selected = {"selection_rule": SELECTION_RULE, "selected": best["label"], "selected_at": stamp["created_utc"],
                    "commit": stamp["git"]["commit"],
                    "test_configs": [NAIVE.to_dict(), RetrievalConfig(**best["config"]).to_dict()]}
        (OUT / "selected.json").write_text(json.dumps(selected, indent=2) + "\n", encoding="utf-8", newline="\n")
        print("selected:", best["label"])
    else:
        payload = {**stamp, "results": results, "per_question": per_question}
        (OUT / "test_results.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
