"""Record a deliberate override of the rule-selected retrieval configuration (dev only).

    python -m finrag.eval.select_retrieval --label structure/hybrid/routed/norerank --reason "..."

Keeps the rule's pick ("rule_selected") next to the final choice, with the reason and time,
so the decision trail survives. Refuses to run once the test split has been scored.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from finrag import config, provenance
from finrag.eval.retrieval_eval import NAIVE, OUT
from finrag.retrieval.pipeline import RetrievalConfig


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--label", required=True)
    parser.add_argument("--reason", required=True)
    args = parser.parse_args(argv)
    if (OUT / "test_results.json").exists():
        raise SystemExit("test split already scored; the selection can no longer change")
    ablation = json.loads((OUT / "dev_ablation.json").read_text(encoding="utf-8"))
    chosen = next((r for r in ablation["results"] if r["label"] == args.label), None)
    if chosen is None:
        raise SystemExit(f"{args.label} is not a configuration in the dev ablation")
    selected = json.loads((OUT / "selected.json").read_text(encoding="utf-8"))
    selected.update({
        "rule_selected": ablation["selected"],
        "selected": args.label,
        "override": {"reason": args.reason, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                     "commit": provenance.git_state()["commit"],
                     "dev_metrics": {"rule_selected": next(r["metrics"] for r in ablation["results"]
                                                           if r["label"] == ablation["selected"]),
                                     "selected": chosen["metrics"]}},
        "test_configs": [NAIVE.to_dict(), RetrievalConfig(**chosen["config"]).to_dict()],
    })
    (OUT / "selected.json").write_text(json.dumps(selected, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: selected[k] for k in ("rule_selected", "selected")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
