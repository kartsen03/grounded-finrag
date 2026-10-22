"""Answer evaluation: judge, judge-human agreement, abstention threshold, probes, test scoring.

    python -m finrag.eval.answer_eval judge --split dev        # judge every non-abstained answer
    python -m finrag.eval.answer_eval agreement                # needs data/labels/dev_human_labels.json
    python -m finrag.eval.answer_eval tune                     # dev: abstention threshold + curve
    python -m finrag.eval.answer_eval probes                   # hallucination rate on unanswerable probes
    python -m finrag.eval.answer_eval report --split dev|test  # metrics per configuration

Threshold rule (fixed before tuning): on dev answers of the "best" configuration, abstain when
support < t, and choose t maximizing (correct answers - incorrect answers); abstaining scores 0.
That is the same as answering only when an answer is more likely right than wrong.
"""

from __future__ import annotations

import argparse
import json

from finrag import config, corpus, provenance
from finrag.answer.pipeline import INSUFFICIENT, AnswerConfig, Answerer
from finrag.eval import metrics
from finrag.eval.answer_runs import RUNS, configs
from finrag.eval.judge import cohen_kappa, judge
from finrag.gateway_client import GatewayClient
from finrag.retrieval.pipeline import Retriever
from finrag.retrieval.store import VectorStore

JUDGED = config.REPO_ROOT / "runs" / "judged"
OUT = config.RESULTS_DIR / "answers"
THRESHOLD_FILE = OUT / "abstention_threshold.json"
SCORING_FILE = OUT / "scoring_choice.json"


def judge_field() -> str:
    """Which judge verdict counts as correct: chosen on dev from judge-human agreement, before test.
    "judge_correct" = raw LLM verdict; "correct" = verdict with the 1% numeric tolerance override."""
    if SCORING_FILE.exists():
        return json.loads(SCORING_FILE.read_text(encoding="utf-8"))["field"]
    return "correct"


def is_correct(row: dict) -> bool:
    return bool(row["judge"] and row["judge"][judge_field()])
THRESHOLD_RULE = "dev, config best: abstain if support < t; t maximizes (#correct - #incorrect) among answered"
PROBES = config.DATA_DIR / "probes" / "unanswerable_v1.jsonl"

# Free-text answers (naive) often decline in words. A probe counts as a hallucination only when the
# answer commits to an answer for the company and period asked, including presenting another period's
# or company's figure as the answer.
COMMITS_SYSTEM = """You check answers to questions that cannot be answered from the available documents.
Decide whether the answer COMMITS to an answer for the exact company and period asked: it states a value,
a yes/no, or a fact as the answer, including when it presents a figure for a different period or company
as if it answered the question. If the answer says the information is not available (even if it mentions
related figures as context without presenting them as the answer), it does NOT commit.
Reply with JSON only."""
COMMITS_SCHEMA = {"type": "object", "properties": {"reason": {"type": "string"}, "commits": {"type": "boolean"}},
                  "required": ["reason", "commits"]}


def commits_to_answer(gateway: GatewayClient, question: str, answer: str, request_id: str) -> dict:
    reply = gateway.chat([{"role": "system", "content": COMMITS_SYSTEM},
                          {"role": "user", "content": f"Question: {question}\n\nAnswer: {answer}"}],
                         "local-chat", request_id=request_id, temperature=0.0, seed=0, max_tokens=200,
                         json_schema=COMMITS_SCHEMA)
    try:
        data = json.loads(reply.content)
    except json.JSONDecodeError:
        data = {"commits": True, "reason": "classifier reply was not valid JSON; counted as committing"}
    return {"commits": bool(data.get("commits")), "reason": data.get("reason", "")}


def _read(path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _write_json(path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")


# ------------------------------------------------------------------ judging


def run_judge(split: str) -> None:
    gateway = GatewayClient()
    out_dir = JUDGED / split
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in configs():
        answers = _read(RUNS / split / f"{name}.jsonl")
        path = out_dir / f"{name}.jsonl"
        done = {r["financebench_id"] for r in _read(path)}
        with path.open("a", encoding="utf-8", newline="\n") as f:
            for rec in answers:
                qid = rec["financebench_id"]
                if qid in done:
                    continue
                q = corpus.questions()[qid]
                verdict = None
                if not rec["abstained"]:
                    verdict = judge(gateway, q["question"], q["answer"], rec["answer"], f"judge-{split}-{name}-{qid}")
                f.write(json.dumps({"financebench_id": qid, "verdict": verdict}) + "\n")
                f.flush()
        print(f"judged {split}/{name}", flush=True)


def _joined(split: str, name: str) -> list[dict]:
    verdicts = {r["financebench_id"]: r["verdict"] for r in _read(JUDGED / split / f"{name}.jsonl")}
    rows = []
    for rec in _read(RUNS / split / f"{name}.jsonl"):
        q = corpus.questions()[rec["financebench_id"]]
        rows.append({**rec, "question_type": q["question_type"], "judge": verdicts.get(rec["financebench_id"]),
                     "gold": corpus.evidence_pages(q)})
    return rows


# ------------------------------------------------------------------ scoring


def apply_threshold(rows: list[dict], t: float | None) -> list[dict]:
    if t is None:
        return rows
    out = []
    for r in rows:
        if not r["abstained"] and r["support"] is not None and r["support"] < t:
            r = {**r, "abstained": True, "abstain_reason": "weak_retrieval_support", "answer": INSUFFICIENT}
        out.append(r)
    return out


def score(rows: list[dict]) -> dict:
    n = len(rows)
    answered = [r for r in rows if not r["abstained"]]
    correct = [r for r in answered if is_correct(r)]
    cited = [(r, c) for r in answered for c in r.get("citations") or []]
    gold_hits = sum(1 for r, c in cited if (c[0], c[1] - 1) in r["gold"])
    reasons: dict[str, int] = {}
    for r in rows:
        if r["abstained"]:
            reasons[r.get("abstain_reason", "?")] = reasons.get(r.get("abstain_reason", "?"), 0) + 1
    verif = [r["verification"] for r in answered if r.get("verification")]
    return {
        "n": n, "answered": len(answered), "abstained": n - len(answered), "correct": len(correct),
        "accuracy": round(len(correct) / n, 4) if n else None,
        "precision_when_answering": round(len(correct) / len(answered), 4) if answered else None,
        "abstention_rate": round((n - len(answered)) / n, 4) if n else None,
        "accuracy_ci95": metrics.bootstrap_ci([float(r in correct) for r in rows]) if n else None,
        "abstain_reasons": reasons,
        "citations": len(cited),
        "citation_precision_gold_pages": round(gold_hits / len(cited), 4) if cited else None,
        "repaired_answers": sum(1 for v in verif if v["repaired"]),
        "answers_with_ungrounded_numbers": sum(1 for v in verif if v["ungrounded_numbers"]),
        "latency_ms_total": {"p50": metrics.percentile([r["timings_ms"]["total"] for r in rows], 0.5),
                             "p95": metrics.percentile([r["timings_ms"]["total"] for r in rows], 0.95)},
        "llm_tokens": {"prompt": sum(r["usage"]["prompt_tokens"] for r in rows),
                       "completion": sum(r["usage"]["completion_tokens"] for r in rows)},
    }


def score_config(split: str, name: str, t: float | None) -> dict:
    rows = apply_threshold(_joined(split, name), t)
    by_type = {qt: score([r for r in rows if r["question_type"] == qt])
               for qt in sorted({r["question_type"] for r in rows})}
    return {"overall": score(rows), "by_question_type": by_type,
            "modes": {m: sum(1 for r in rows if r["mode"] == m) for m in sorted({r["mode"] for r in rows})}}


def load_threshold() -> float | None:
    return json.loads(THRESHOLD_FILE.read_text(encoding="utf-8"))["threshold"] if THRESHOLD_FILE.exists() else None


# ------------------------------------------------------------------ commands


def agreement() -> None:
    labels = json.loads((config.DATA_DIR / "labels" / "dev_human_labels.json").read_text(encoding="utf-8"))["labels"]
    human, raw, tol = [], [], []
    for lab in labels:
        verdict = next(r["verdict"] for r in _read(JUDGED / "dev" / f"{lab['config']}.jsonl")
                       if r["financebench_id"] == lab["financebench_id"])
        human.append(lab["label"] == "CORRECT")
        raw.append(verdict["judge_correct"])
        tol.append(verdict["correct"])
    def stats(pred):
        return {"percent_agreement": round(sum(h == p for h, p in zip(human, pred)) / len(human), 4),
                "cohen_kappa": round(cohen_kappa(human, pred), 4),
                "confusion": {"both_correct": sum(h and p for h, p in zip(human, pred)),
                              "both_incorrect": sum((not h) and (not p) for h, p in zip(human, pred)),
                              "judge_correct_human_incorrect": sum((not h) and p for h, p in zip(human, pred)),
                              "judge_incorrect_human_correct": sum(h and (not p) for h, p in zip(human, pred))}}
    payload = {**provenance.stamp(step="judge_human_agreement"), "n": len(human),
               "human_correct_rate": round(sum(human) / len(human), 4),
               "judge_raw": stats(raw), "judge_plus_tolerance": stats(tol)}
    _write_json(OUT / "judge_agreement.json", payload)
    print(json.dumps({k: payload[k] for k in ("n", "judge_raw", "judge_plus_tolerance")}, indent=2))


def tune() -> None:
    if (OUT / "test_report.json").exists():
        raise SystemExit("test already scored; the threshold can no longer change")
    rows = _joined("dev", "best")
    candidates = sorted({r["support"] for r in rows if r["support"] is not None})
    curve = []
    for t in [None] + candidates:
        s = score(apply_threshold(rows, t))
        curve.append({"threshold": t, "coverage": round(s["answered"] / s["n"], 4),
                      "precision_when_answering": s["precision_when_answering"], "correct": s["correct"],
                      "incorrect": s["answered"] - s["correct"], "utility": s["correct"] - (s["answered"] - s["correct"])})
    best = max(curve, key=lambda p: (p["utility"], p["coverage"]))
    payload = {**provenance.stamp(step="abstention_threshold_dev"), "rule": THRESHOLD_RULE,
               "scoring_field": judge_field(),
               "threshold": best["threshold"], "chosen_point": best, "curve": curve}
    _write_json(THRESHOLD_FILE, payload)
    print("threshold:", best)


def probes() -> None:
    gateway = GatewayClient()
    answerer = Answerer(gateway, Retriever(gateway, VectorStore()))
    t = load_threshold()
    cfgs = configs()
    rows = {}
    probes_list = _read(PROBES)
    for name in ("naive", "best"):
        base = cfgs[name]
        cfg = AnswerConfig(base.name, base.retrieval, base.mode, base.context_k, base.repair,
                           t if name == "best" else None)
        rows[name] = [{"probe_id": p["probe_id"], "kind": p["kind"],
                       **answerer.answer(p["question"], cfg, request_id=f"probe-{name}-{p['probe_id']}")}
                      for p in probes_list]
    questions = {p["probe_id"]: p["question"] for p in probes_list}
    for name, rs in rows.items():
        for r in rs:
            r["classification"] = None if r["abstained"] else commits_to_answer(
                gateway, questions[r["probe_id"]], r["answer"], f"probe-classify-{name}-{r['probe_id']}")

    def rate(rs):
        answered = [r for r in rs if not r["abstained"]]
        halluc = [r for r in answered if r["classification"]["commits"]]
        return {"n": len(rs), "not_abstained": len(answered), "hallucinated": len(halluc),
                "hallucination_rate": round(len(halluc) / len(rs), 4),
                "by_kind": {k: sum(1 for r in halluc if r["kind"] == k) for k in sorted({r["kind"] for r in rs})},
                "abstain_reasons": {x: sum(1 for r in rs if r.get("abstain_reason") == x)
                                    for x in sorted({r.get("abstain_reason") for r in rs if r["abstained"]})}}
    payload = {**provenance.stamp(step="unanswerable_probes"), "probe_file": "data/probes/unanswerable_v1.jsonl",
               "threshold_used_for_best": t, "naive": rate(rows["naive"]), "best": rate(rows["best"]),
               "classified_by": "local-chat via gateway, prompt COMMITS_SYSTEM in answer_eval.py",
               "per_probe": {n: [{"probe_id": r["probe_id"], "abstained": r["abstained"],
                                  "commits": None if r["abstained"] else r["classification"]["commits"],
                                  "reason": None if r["abstained"] else r["classification"]["reason"]} for r in rs]
                             for n, rs in rows.items()}}
    _write_json(OUT / "probes.json", payload)
    (config.REPO_ROOT / "runs" / "probes.jsonl").write_text(
        "\n".join(json.dumps(r) for rs in rows.values() for r in rs) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: payload[k] for k in ("naive", "best")}, indent=2))


def report(split: str) -> None:
    target = OUT / f"{split}_report.json"
    if split == "test" and target.exists():
        raise SystemExit(f"{target} exists: the test split has already been scored")
    t = load_threshold()
    results = {}
    for name in configs():
        results[name] = {"no_threshold": score_config(split, name, None)}
        if name in ("best", "best_model_arith", "oracle") and t is not None:
            results[name]["with_threshold"] = score_config(split, name, t)
    payload = {**provenance.stamp(step=f"answer_report_{split}"), "split": split, "threshold": t,
               "scoring_field": judge_field(),
               "judge": "local-chat (qwen2.5:7b-instruct-q4_K_M) via gateway, rubric docs/judge_rubric.md, "
                        "1% tolerance check", "results": results}
    _write_json(target, payload)
    for name, r in results.items():
        o = r["no_threshold"]["overall"]
        print(f"{name:18s} acc={o['accuracy']} prec_ans={o['precision_when_answering']} abst={o['abstention_rate']} "
              f"cite_prec={o['citation_precision_gold_pages']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("judge", "agreement", "tune", "probes", "report"))
    parser.add_argument("--split", choices=("dev", "test"), default="dev")
    args = parser.parse_args(argv)
    {"judge": lambda: run_judge(args.split), "agreement": agreement, "tune": tune, "probes": probes,
     "report": lambda: report(args.split)}[args.command]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
