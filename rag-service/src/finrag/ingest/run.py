"""Ingest the corpus: parse every PDF, log parsing issues, build both chunk sets.

    python -m finrag.ingest.run [--workers 10] [--docs 3M_2018_10K,AMD_2022_10K]

Writes data/processed/ (gitignored: derived from CC BY-NC PDFs):
    pages/<doc>.json.gz, parse_issues.jsonl, chunks_fixed.jsonl, chunks_structure.jsonl
and results/ingestion/ (committed: counts and provenance only):
    summary.json, evidence_page_check.json
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import gzip
import json
import os
import time
from collections import Counter

from finrag import config, corpus, provenance
from finrag.ingest import chunking, evidence_check
from finrag.ingest.pdf_parse import parse_pdf


def _ingest_doc(doc_name: str) -> dict:
    meta = corpus.all_doc_meta()[doc_name]
    t0 = time.perf_counter()
    parsed, issues = parse_pdf(config.PDF_DIR / f"{doc_name}.pdf", doc_name)
    parse_s = time.perf_counter() - t0
    pages = [{"page_idx": p.page_idx, "blocks": p.blocks} for p in parsed]
    chunks = {name: [c.to_dict() for c in fn(meta, pages)] for name, fn in chunking.STRATEGIES.items()}
    return {"doc_name": doc_name, "pages": pages, "issues": issues, "chunks": chunks, "parse_seconds": parse_s}


def _percentile(values: list[int], q: float) -> int:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workers", type=int, default=max(1, min(10, (os.cpu_count() or 2) - 2)))
    parser.add_argument("--docs", help="comma-separated subset of document names")
    args = parser.parse_args(argv)

    docs = [d.doc_name for d in corpus.corpus_docs()]
    if args.docs:
        wanted = set(args.docs.split(","))
        docs = [d for d in docs if d in wanted]
    chunking.tokenizer()  # download once before the workers start

    out = config.PROCESSED_DIR
    (out / "pages").mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    results: list[dict] = []
    with cf.ProcessPoolExecutor(max_workers=args.workers) as pool:
        for res in pool.map(_ingest_doc, docs):
            with gzip.open(out / "pages" / f"{res['doc_name']}.json.gz", "wt", encoding="utf-8") as f:
                json.dump(res["pages"], f)
            results.append(res)
            print(f"{res['doc_name']}: {len(res['pages'])} pages, {res['parse_seconds']:.1f}s", flush=True)
    wall = time.perf_counter() - started

    issues = [i for r in results for i in r["issues"]]
    with (out / "parse_issues.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for issue in issues:
            f.write(json.dumps(issue) + "\n")
    chunk_stats = {}
    for name in chunking.STRATEGIES:
        chunks = [c for r in results for c in r["chunks"][name]]
        with (out / f"chunks_{name}.jsonl").open("w", encoding="utf-8", newline="\n") as f:
            for c in chunks:
                f.write(json.dumps(c) + "\n")
        tokens = [c["n_tokens"] for c in chunks]
        chunk_stats[name] = {
            "chunks": len(chunks),
            "tokens_p50": _percentile(tokens, 0.5),
            "tokens_p95": _percentile(tokens, 0.95),
            "tokens_max": max(tokens),
            "share_with_table": round(sum(c["has_table"] for c in chunks) / len(chunks), 4),
            "share_spanning_pages": round(sum(len(c["pages"]) > 1 for c in chunks) / len(chunks), 4),
            "share_with_section": round(sum(c["section"] is not None for c in chunks) / len(chunks), 4),
        }

    blocks = Counter(b["kind"] for r in results for p in r["pages"] for b in p["blocks"])
    by_type = Counter(i["type"] for i in issues)
    examples = {t: [f"{i['doc_name']} p{i['page_idx']}: {i['detail']}" for i in issues if i["type"] == t][:8]
                for t in sorted(by_type)}
    summary = provenance.stamp(
        "pdfplumber", "pdfminer.six", "tokenizers",
        step="ingestion",
        settings={"chunk_tokens": chunking.CHUNK_TOKENS, "overlap_tokens": chunking.OVERLAP_TOKENS,
                  "tokenizer": f"{config.EMBED_MODEL}@{config.EMBED_MODEL_REVISION}", "workers": args.workers},
        documents=len(results),
        pages=sum(len(r["pages"]) for r in results),
        blocks=dict(sorted(blocks.items())),
        wall_seconds=round(wall, 1),
        parse_seconds_total=round(sum(r["parse_seconds"] for r in results), 1),
        issues_by_type=dict(sorted(by_type.items())),
        docs_with_issue={t: len({i["doc_name"] for i in issues if i["type"] == t}) for t in sorted(by_type)},
        issue_examples=examples,
        chunks=chunk_stats,
    )
    res_dir = config.RESULTS_DIR / "ingestion"
    res_dir.mkdir(parents=True, exist_ok=True)
    (res_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n")

    page_text = {(r["doc_name"], p["page_idx"]): "\n".join(b["text"] for b in p["blocks"])
                 for r in results for p in r["pages"]}
    qs = {qid: q for qid, q in corpus.questions().items() if q["doc_name"] in set(docs)}
    check = {**provenance.stamp(step="evidence_page_check"), **evidence_check.check(qs, page_text)}
    (res_dir / "evidence_page_check.json").write_text(json.dumps(check, indent=2) + "\n", encoding="utf-8",
                                                      newline="\n")
    print(json.dumps({k: summary[k] for k in ("documents", "pages", "wall_seconds", "issues_by_type", "chunks")},
                     indent=2))
    print("evidence check:", check["outcomes"], "median coverage at p:", check["median_coverage_at_p"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
