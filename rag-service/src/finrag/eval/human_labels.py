"""Hand labels for validating the LLM judge.

    python -m finrag.eval.human_labels sheet    # write runs/labeling/dev_label_sheet.csv
    python -m finrag.eval.human_labels import   # read the filled sheet -> data/labels/dev_human_labels.json

The sheet holds 40 non-abstained dev answers, sampled with a fixed seed and spread evenly over
the naive, best, best_model_arith and oracle configurations, in shuffled order. It shows the
question, the reference answer and the system answer, never the judge's verdict. Fill the
"label" column with CORRECT or INCORRECT using the rubric in docs/judge_rubric.md.

The sheet contains FinanceBench text, so it stays under runs/ (gitignored); only IDs and labels
are committed.
"""

from __future__ import annotations

import csv
import json
import random
import sys

from finrag import config, corpus

SHEET = config.REPO_ROOT / "runs" / "labeling" / "dev_label_sheet.csv"
LABELS = config.DATA_DIR / "labels" / "dev_human_labels.json"
CONFIGS = ("naive", "best", "best_model_arith", "oracle")
N_ITEMS = 40
SEED = 20261021


def _answers(name: str) -> list[dict]:
    path = config.REPO_ROOT / "runs" / "answers" / "dev" / f"{name}.jsonl"
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def sheet() -> None:
    rng = random.Random(SEED)
    items = []
    per_config = N_ITEMS // len(CONFIGS)
    for name in CONFIGS:
        answered = [r for r in _answers(name) if not r["abstained"]]
        for r in rng.sample(answered, per_config):
            items.append((name, r))
    rng.shuffle(items)
    SHEET.parent.mkdir(parents=True, exist_ok=True)
    with SHEET.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["item", "financebench_id", "config", "question", "reference_answer", "system_answer", "label",
                    "note"])
        for i, (name, r) in enumerate(items, start=1):
            q = corpus.questions()[r["financebench_id"]]
            w.writerow([i, r["financebench_id"], name, q["question"], q["answer"], r["answer"], "", ""])
    print(f"wrote {SHEET} ({len(items)} items)")


def import_labels() -> None:
    with SHEET.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    labels = []
    for row in rows:
        label = row["label"].strip().upper()
        if label not in ("CORRECT", "INCORRECT"):
            raise SystemExit(f"item {row['item']}: label must be CORRECT or INCORRECT, got {row['label']!r}")
        labels.append({"item": int(row["item"]), "financebench_id": row["financebench_id"], "config": row["config"],
                       "label": label, "note": row["note"].strip()})
    LABELS.parent.mkdir(parents=True, exist_ok=True)
    LABELS.write_text(json.dumps({"labeler": "Karthik Sengupta", "rubric": "docs/judge_rubric.md", "seed": SEED,
                                  "labels": labels}, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"imported {len(labels)} labels -> {LABELS}")


if __name__ == "__main__":
    {"sheet": sheet, "import": import_labels}[sys.argv[1]]()
