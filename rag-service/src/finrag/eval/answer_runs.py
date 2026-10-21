"""Generate answers for a split under the comparison configurations.

    python -m finrag.eval.answer_runs --split dev [--configs naive,best,best_model_arith,oracle]

Configurations
  naive             naive retrieval (fixed chunks, dense, no routing) + plain prompt, no verification
  best              selected retrieval + auto mode (extract-then-compute for numeric questions,
                    grounded claims otherwise) + citation verification and one repair
  best_model_arith  as best, but always grounded claims: the model does any arithmetic itself
  oracle            gold evidence pages as context + the same answering as best

Records go to runs/answers/<split>/<config>.jsonl (gitignored: they contain FinanceBench
question text). The run resumes: questions already answered are skipped. Abstention by
support threshold is applied later, after the threshold is tuned on dev.
"""

from __future__ import annotations

import argparse
import json

from finrag import config, corpus, provenance
from finrag.answer.pipeline import AnswerConfig, Answerer
from finrag.eval.retrieval_eval import NAIVE
from finrag.gateway_client import GatewayClient
from finrag.retrieval.pipeline import RetrievalConfig, Retriever
from finrag.retrieval.store import VectorStore

RUNS = config.REPO_ROOT / "runs" / "answers"


def configs() -> dict[str, AnswerConfig]:
    selected = json.loads((config.RESULTS_DIR / "retrieval" / "selected.json").read_text(encoding="utf-8"))
    best_retrieval = RetrievalConfig(**selected["test_configs"][1])
    naive_retrieval = RetrievalConfig(**{**NAIVE.to_dict(), "top_k": 5})
    best_retrieval = RetrievalConfig(**{**best_retrieval.to_dict(), "top_k": 5})
    return {
        "naive": AnswerConfig("naive", naive_retrieval, mode="naive", repair=False),
        "best": AnswerConfig("best", best_retrieval, mode="auto"),
        "best_model_arith": AnswerConfig("best_model_arith", best_retrieval, mode="grounded"),
        "oracle": AnswerConfig("oracle", None, mode="auto"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--split", choices=("dev", "test"), required=True)
    parser.add_argument("--configs", default="naive,best,best_model_arith,oracle")
    args = parser.parse_args(argv)
    out_dir = RUNS / args.split
    out_dir.mkdir(parents=True, exist_ok=True)
    gateway = GatewayClient()
    answerer = Answerer(gateway, Retriever(gateway, VectorStore()))
    all_cfgs = configs()
    for name in args.configs.split(","):
        cfg = all_cfgs[name]
        path = out_dir / f"{name}.jsonl"
        done = set()
        if path.exists():
            with path.open(encoding="utf-8") as f:
                done = {json.loads(line)["financebench_id"] for line in f if line.strip()}
        meta = out_dir / f"{name}.meta.json"
        if not meta.exists():
            meta.write_text(json.dumps(provenance.stamp("httpx", step=f"answers_{args.split}_{name}",
                                                        config=cfg.to_dict(), llm="local-chat -> ollama "
                                                        "qwen2.5:7b-instruct-q4_K_M"), indent=2) + "\n",
                            encoding="utf-8", newline="\n")
        todo = [q for q in corpus.split()[args.split] if q not in done]
        print(f"{name}: {len(done)} done, {len(todo)} to go", flush=True)
        with path.open("a", encoding="utf-8", newline="\n") as f:
            for qid in todo:
                q = corpus.questions()[qid]
                rec = answerer.answer(q["question"], cfg, gold=corpus.evidence_pages(q),
                                      request_id=f"{args.split}-{name}-{qid}")
                rec["financebench_id"] = qid
                f.write(json.dumps(rec) + "\n")
                f.flush()
                print(f"{name} {qid} mode={rec['mode']} abstained={rec['abstained']} "
                      f"total_ms={rec['timings_ms']['total']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
