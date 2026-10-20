"""Make the fixed dev/test split of the FinanceBench open-source sample.

Stratified by question_type and seeded: inside each question type the IDs are
sorted, shuffled with random.Random(SEED), and the first half goes to dev. All
design choices are made on dev; test is scored once per final configuration.

The output holds question IDs only (no FinanceBench text) and is committed:

    python scripts/make_split.py           # write data/splits/financebench_split_v1.json
    python scripts/make_split.py --check   # fail if regenerating gives a different file
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

SEED = 20261020
DEV_FRACTION = 0.5
SPLIT_NAME = "financebench_split_v1"

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "financebench" / "data"
QUESTIONS = RAW / "financebench_open_source.jsonl"
DOC_INFO = RAW / "financebench_document_information.jsonl"
OUT = ROOT / "data" / "splits" / f"{SPLIT_NAME}.json"


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def stratified_split(rows: list[dict], seed: int, dev_fraction: float) -> tuple[list[str], list[str]]:
    by_type: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        by_type[row["question_type"]].append(row["financebench_id"])
    rng = random.Random(seed)
    dev: list[str] = []
    test: list[str] = []
    for qtype in sorted(by_type):
        ids = sorted(by_type[qtype])
        rng.shuffle(ids)
        k = round(len(ids) * dev_fraction)
        dev += ids[:k]
        test += ids[k:]
    return sorted(dev), sorted(test)


def describe(ids: list[str], rows_by_id: dict[str, dict], doc_type: dict[str, str]) -> dict:
    rows = [rows_by_id[i] for i in ids]
    return {
        "total": len(rows),
        "question_type": dict(sorted(Counter(r["question_type"] for r in rows).items())),
        "doc_type": dict(sorted(Counter(doc_type[r["doc_name"]] for r in rows).items())),
        "documents": len({r["doc_name"] for r in rows}),
        "companies": len({r["company"] for r in rows}),
    }


def build() -> dict:
    rows = read_jsonl(QUESTIONS)
    doc_type = {d["doc_name"]: d["doc_type"] for d in read_jsonl(DOC_INFO)}
    rows_by_id = {r["financebench_id"]: r for r in rows}
    if len(rows_by_id) != len(rows):
        raise SystemExit("duplicate financebench_id values")
    dev, test = stratified_split(rows, SEED, DEV_FRACTION)

    dev_docs = {rows_by_id[i]["doc_name"] for i in dev}
    test_docs = {rows_by_id[i]["doc_name"] for i in test}
    dev_cos = {rows_by_id[i]["company"] for i in dev}
    test_cos = {rows_by_id[i]["company"] for i in test}
    return {
        "name": SPLIT_NAME,
        "source": {
            "file": "data/financebench_open_source.jsonl",
            "sha256": hashlib.sha256(QUESTIONS.read_bytes()).hexdigest(),
        },
        "method": "stratified by question_type; per stratum: sort IDs, random.Random(seed).shuffle, "
                  "first round(n * dev_fraction) to dev",
        "seed": SEED,
        "dev_fraction": DEV_FRACTION,
        "counts": {
            "dev": describe(dev, rows_by_id, doc_type),
            "test": describe(test, rows_by_id, doc_type),
        },
        # Not used for splitting; recorded so the overlap is visible when reading results.
        "overlap": {
            "documents_in_both": len(dev_docs & test_docs),
            "test_questions_on_a_dev_document": sum(rows_by_id[i]["doc_name"] in dev_docs for i in test),
            "companies_in_both": len(dev_cos & test_cos),
        },
        "dev": dev,
        "test": test,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="verify the committed split instead of writing it")
    args = parser.parse_args(argv)

    text = json.dumps(build(), indent=2) + "\n"
    if args.check:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            print(f"{OUT.relative_to(ROOT)} does not match a fresh regeneration", file=sys.stderr)
            return 1
        print(f"{OUT.relative_to(ROOT)} matches")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    split = json.loads(text)
    print(json.dumps({"counts": split["counts"], "overlap": split["overlap"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
