"""Render committed results JSON as Markdown tables. No number in the docs is typed by hand.

    python -m finrag.eval.report retrieval   # -> results/retrieval/dev_ablation.md
"""

from __future__ import annotations

import json
import sys

from finrag import config


def _fmt(x: float) -> str:
    return f"{x:.4f}"


def retrieval_table() -> str:
    data = json.loads((config.RESULTS_DIR / "retrieval" / "dev_ablation.json").read_text(encoding="utf-8"))
    git, machine = data["git"], data["machine"]
    lines = [
        "# Retrieval ablation (dev split)",
        "",
        f"Generated from `results/retrieval/dev_ablation.json` (values exactly as stored; hit@k = hits out of 75). Commit `{git['commit'][:7]}`"
        f"{' (dirty)' if git['dirty'] else ''}, {data['created_utc']}. {data['n_questions']} dev questions.",
        f"Embeddings `{data['embed_model']}`, re-ranker `{data['rerank_model']}`; GPU {machine['gpu']}, "
        f"power plan {machine['power_plan']}.",
        "",
        f"Selection rule (fixed before the run): {data['selection_rule']}. **Selected: `{data['selected']}`**.",
        "",
        "| Chunking | Retriever | Routing | Re-rank | hit@1 | hit@3 | hit@5 | hit@10 | MRR@10 | hit@5 95% CI "
        "| p50 ms | p95 ms |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in data["results"]:
        c, m, lat = r["config"], r["metrics"], r["latency_ms"]["total"]
        lo, hi = r["ci95"]["hit@5"]
        mark = " **(selected)**" if r["label"] == data["selected"] else ""
        lines.append(f"| {c['strategy']} | {c['retriever']} | {'yes' if c['routing'] else 'no'} | "
                     f"{'yes' if c['rerank'] else 'no'}{mark} | {_fmt(m['hit@1'])} | {_fmt(m['hit@3'])} | "
                     f"{_fmt(m['hit@5'])} | {_fmt(m['hit@10'])} | {_fmt(m['mrr@10'])} | {lo:.4f}-{hi:.4f} | "
                     f"{lat['p50']} | {lat['p95']} |")
    best = next(r for r in data["results"] if r["label"] == data["selected"])
    lines += ["", f"## Per-stage latency of the selected configuration (ms)", "", "| Stage | p50 | p95 |",
              "|---|---|---|"]
    for stage, v in best["latency_ms"].items():
        lines.append(f"| {stage} | {v['p50']} | {v['p95']} |")
    routed = [r for r in data["results"] if r["routing"]]
    if routed:
        rt = routed[0]["routing"]
        lines += ["", f"Routing applied a filter to {rt['filtered']} of {data['n_questions']} questions; the gold "
                      f"document was inside the filter for {rt['gold_doc_in_filter']} of them."]
    lines += ["", f"HNSW vs exact search, unfiltered dense top-50 overlap: {data['hnsw']}"]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    what = (argv or sys.argv[1:] or ["retrieval"])[0]
    if what == "retrieval":
        out = config.RESULTS_DIR / "retrieval" / "dev_ablation.md"
        out.write_text(retrieval_table(), encoding="utf-8", newline="\n")
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
