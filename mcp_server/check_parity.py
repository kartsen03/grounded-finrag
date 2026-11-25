"""Does answer_question behave like the evaluated pipeline? Compare its abstain/answer decision on
the latency-benchmark questions with the committed dev run of the best configuration.

    python mcp_server/check_parity.py      # reads results/mcp/latency.json and runs/answers/dev/best.jsonl

The evaluated decision is the one scored in the README: abstain if the model abstained or the
support score is below the dev-tuned threshold (results/answers/abstention_threshold.json).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "rag-service" / "src"))

from finrag import provenance  # noqa: E402

LATENCY = ROOT / "results" / "mcp" / "latency.json"
DEV_RUN = ROOT / "runs" / "answers" / "dev" / "best.jsonl"
THRESHOLD = ROOT / "results" / "answers" / "abstention_threshold.json"
OUT = ROOT / "results" / "mcp" / "parity_dev.json"


def evaluated_abstains(rec: dict, threshold: float) -> bool:
    """Same rule as finrag.eval.answer_eval.apply_threshold."""
    support = rec["support"]
    return bool(rec["abstained"]) or (support is not None and support < threshold)


def main() -> int:
    bench = json.loads(LATENCY.read_text(encoding="utf-8"))
    threshold = json.loads(THRESHOLD.read_text(encoding="utf-8"))["threshold"]
    dev = {r["financebench_id"]: r for r in map(json.loads, DEV_RUN.read_text(encoding="utf-8").splitlines())}
    rows = [{"financebench_id": c["financebench_id"], "mcp_abstained": c["abstained"],
             "evaluated_abstained": evaluated_abstains(dev[c["financebench_id"]], threshold)}
            for c in bench["calls"]["answer_question"]]
    same = sum(r["mcp_abstained"] == r["evaluated_abstained"] for r in rows)
    record = provenance.stamp(step="mcp-parity-dev", latency_file_commit=bench["git"]["commit"],
                              threshold=threshold, compared=len(rows), same_decision=same, rows=rows)
    OUT.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"same abstain/answer decision on {same} of {len(rows)} questions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
