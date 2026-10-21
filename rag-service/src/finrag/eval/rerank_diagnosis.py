"""Why does cross-encoder re-ranking hurt on routed queries? (dev split only)

For structure chunks + dense + routing, compare the top-5 before and after re-ranking:
the share of retrieved chunks that contain a table, and whether the gold evidence page's
chunks are tables. Writes results/retrieval/dev_rerank_diagnosis.json.
"""

from __future__ import annotations

import json

from finrag import config, corpus, provenance
from finrag.gateway_client import GatewayClient
from finrag.retrieval.pipeline import RetrievalConfig, Retriever
from finrag.retrieval.store import VectorStore


def main() -> int:
    retriever = Retriever(GatewayClient(), VectorStore())
    base = RetrievalConfig("structure", "dense", routing=True, rerank=False, top_k=5)
    rer = RetrievalConfig("structure", "dense", routing=True, rerank=True, top_k=5)
    rows = []
    for qid in corpus.split()["dev"]:
        q = corpus.questions()[qid]
        gold = corpus.evidence_pages(q)
        a = retriever.retrieve(q["question"], base).hits
        b = retriever.retrieve(q["question"], rer).hits
        rows.append({
            "question_type": q["question_type"],
            "table_share_before": sum(h.chunk["has_table"] for h in a) / len(a),
            "table_share_after": sum(h.chunk["has_table"] for h in b) / len(b),
            "gold_in_top5_before": any((h.chunk["doc_name"], h.chunk["page_idx"]) in gold for h in a),
            "gold_in_top5_after": any((h.chunk["doc_name"], h.chunk["page_idx"]) in gold for h in b),
            "gold_chunks_before_are_tables": [h.chunk["has_table"] for h in a
                                              if (h.chunk["doc_name"], h.chunk["page_idx"]) in gold],
        })
    out = {}
    for qtype in sorted({r["question_type"] for r in rows}) + ["all"]:
        sel = [r for r in rows if qtype == "all" or r["question_type"] == qtype]
        lost = [r for r in sel if r["gold_in_top5_before"] and not r["gold_in_top5_after"]]
        gained = [r for r in sel if not r["gold_in_top5_before"] and r["gold_in_top5_after"]]
        found_gold = [t for r in sel for t in r["gold_chunks_before_are_tables"]]
        out[qtype] = {
            "n": len(sel),
            "table_share_top5_before": round(sum(r["table_share_before"] for r in sel) / len(sel), 4),
            "table_share_top5_after": round(sum(r["table_share_after"] for r in sel) / len(sel), 4),
            "gold_lost_by_rerank": len(lost), "gold_gained_by_rerank": len(gained),
            "gold_chunks_found_before_that_are_tables": f"{sum(found_gold)}/{len(found_gold)}",
        }
    payload = {**provenance.stamp(step="rerank_diagnosis_dev"), "config": base.label, "results": out}
    path = config.RESULTS_DIR / "retrieval" / "dev_rerank_diagnosis.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
