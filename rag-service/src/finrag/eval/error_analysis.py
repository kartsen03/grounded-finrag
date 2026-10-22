"""Failure taxonomy for judged answers (rule-based, so every label can be checked).

    python -m finrag.eval.error_analysis --split dev --config best

Each incorrect or abstained answer gets the first matching category:
  retrieval_miss      no gold evidence page among the sources given to the model
  table_parse_error   a gold page was given, but numbers in the gold evidence text are missing
                      from our parsed text of that page
  wrong_period        the answer cites a filing for a different fiscal period than the gold document
  arithmetic          numeric question answered from the right page but the number is wrong
                      (model arithmetic in grounded mode; extraction or metric definition in extract mode)
  unsupported_claim   the answer states numbers that do not appear on the pages it cites
  abstained_despite_gold_page   abstained (model flag or failed verification) although a gold page
                      was among the sources; failed verification is often a caught hallucination
  other               anything else (reasoning, judgement, ambiguous reference answer)
Writes results/answers/error_analysis_<split>_<config>.json (IDs and counts, no question text).
"""

from __future__ import annotations

import argparse
import gzip
import json
from collections import Counter
from functools import lru_cache

from finrag import config, corpus, provenance
import re

from finrag.answer.numbers import grounded, parse_number
from finrag.eval.answer_eval import _joined, apply_threshold, is_correct, load_threshold
from finrag.retrieval.routing import detect_years

CATEGORIES = ("retrieval_miss", "table_parse_error", "wrong_period", "arithmetic", "unsupported_claim",
              "abstained_despite_gold_page", "other")


# Only formatted figures (thousands separators or decimals) are checked: bare integers in evidence text are
# often printed page numbers (stripped by the parser on purpose) or dates glued together upstream.
_FIGURE = re.compile(r"(?<![A-Za-z\d,.])\(?\$?\d{1,3}(?:,\d{3})+(?:\.\d+)?\)?|\d+\.\d+")


def _figures(text: str) -> list[float]:
    return [v for v in (parse_number(m.group(0)) for m in _FIGURE.finditer(text)) if v is not None]


@lru_cache(maxsize=None)
def _page_text(doc: str, page_idx: int) -> str:
    path = config.PROCESSED_DIR / "pages" / f"{doc}.json.gz"
    with gzip.open(path, "rt", encoding="utf-8") as f:
        pages = json.load(f)
    return "\n".join(b["text"] for b in pages[page_idx]["blocks"])


def _extracted_wrong_year(row: dict, question: str) -> bool:
    """True when no extracted line item's period mentions the latest fiscal year the question asks about."""
    years = detect_years(question)
    if not years or not row.get("raw"):
        return False
    try:
        inputs = json.loads(row["raw"][-1]["raw"]).get("inputs") or []
    except (json.JSONDecodeError, AttributeError):
        return False
    target = max(years)
    marks = (str(target), f"FY{target % 100:02d}", f"'{target % 100:02d}")
    return bool(inputs) and not any(any(m in str(i.get("period", "")) for m in marks) for i in inputs)


def categorize(row: dict) -> str:
    q = corpus.questions()[row["financebench_id"]]
    gold = row["gold"]
    given = {(s["doc_name"], s["page_idx"]) for s in row["sources"]}
    gold_given = gold & given
    if not gold_given:
        return "retrieval_miss"
    for ev in q["evidence"]:
        key = (ev["doc_name"], int(ev["evidence_page_num"]))
        if key in gold_given:
            text = _page_text(*key)
            if any(not grounded(v, text) for v in _figures(ev["evidence_text"])):
                return "table_parse_error"
    if row["abstained"]:
        return "abstained_despite_gold_page"
    meta = corpus.all_doc_meta()
    gold_doc = meta[q["doc_name"]]
    cited_docs = {c[0] for c in row.get("citations") or []}
    if cited_docs and all((meta[d].fiscal_year, meta[d].fiscal_quarter) != (gold_doc.fiscal_year,
                                                                           gold_doc.fiscal_quarter)
                          for d in cited_docs if d in meta):
        return "wrong_period"
    if row["mode"] == "extract" and _extracted_wrong_year(row, q["question"]):
        return "wrong_period"
    if q["question_type"] == "metrics-generated" or row["mode"] == "extract":
        return "arithmetic"
    if row.get("verification") and row["verification"].get("ungrounded_numbers"):
        return "unsupported_claim"
    return "other"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--split", default="dev")
    parser.add_argument("--config", default="best")
    parser.add_argument("--with-threshold", action="store_true",
                        help="apply the tuned abstention threshold first (default: analyze raw answers)")
    args = parser.parse_args(argv)
    rows = apply_threshold(_joined(args.split, args.config), load_threshold() if args.with_threshold else None)
    failures = [r for r in rows if r["abstained"] or not is_correct(r)]
    labeled = [{"financebench_id": r["financebench_id"], "question_type": r["question_type"], "mode": r["mode"],
                "abstained": r["abstained"], "abstain_reason": r.get("abstain_reason"), "category": categorize(r)}
               for r in failures]
    counts = Counter(x["category"] for x in labeled)
    payload = {**provenance.stamp(step=f"error_analysis_{args.split}_{args.config}"), "split": args.split,
               "config": args.config, "threshold_applied": args.with_threshold, "n_questions": len(rows), "n_failures": len(labeled),
               "counts": {c: counts.get(c, 0) for c in CATEGORIES},
               "by_category": {c: [x["financebench_id"] for x in labeled if x["category"] == c] for c in CATEGORIES},
               "failures": labeled}
    out = config.RESULTS_DIR / "answers" / f"error_analysis_{args.split}_{args.config}.json"
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(payload["counts"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
