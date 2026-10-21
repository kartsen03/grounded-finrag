"""Write the README results section from committed results files (between marker comments).

    python -m finrag.eval.readme_tables

Sections whose results file does not exist yet are left out. Values are printed exactly as
stored; nothing here is typed by hand.
"""

from __future__ import annotations

import json
import re

from finrag import config

START, END = "<!-- results:start -->", "<!-- results:end -->"
R = config.RESULTS_DIR


def _load(rel: str) -> dict | None:
    path = R / rel
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _prov(d: dict) -> str:
    g, m = d["git"], d["machine"]
    return (f"commit `{g['commit'][:7]}`{' (dirty)' if g['dirty'] else ''}, {m['gpu'].split(',')[0]}, "
            f"power plan {m['power_plan']}, {d['created_utc'][:10]}")


def retrieval_section() -> list[str]:
    out = []
    dev = _load("retrieval/dev_ablation.json")
    sel = _load("retrieval/selected.json")
    test = _load("retrieval/test_results.json")
    if dev and sel:
        rows = {r["label"]: r for r in dev["results"]}
        out += ["### Retrieval (evidence-page hit@k, 75 questions per split)", "",
                "| Configuration | Split | hit@1 | hit@3 | hit@5 | hit@10 | MRR@10 | hit@5 95% CI | p50 ms |",
                "|---|---|---|---|---|---|---|---|---|"]
        labels = ["fixed/dense/unrouted/norerank", sel["selected"]]
        names = {labels[0]: "naive: fixed chunks, dense", labels[1]: "best: structure chunks, hybrid, routed"}
        for split, data in (("dev", rows), ("test", {r["label"]: r for r in test["results"]} if test else {})):
            for label in labels:
                r = data.get(label)
                if r:
                    m, ci = r["metrics"], r["ci95"]["hit@5"]
                    out.append(f"| {names[label]} | {split} | {m['hit@1']} | {m['hit@3']} | {m['hit@5']} | "
                               f"{m['hit@10']} | {m['mrr@10']} | {ci[0]}-{ci[1]} | {r['latency_ms']['total']['p50']} |")
        out += ["", f"Dev: {_prov(dev)}." + (f" Test: {_prov(test)}." if test else " Test: not scored yet."),
                "All 24 dev configurations: [results/retrieval/dev_ablation.md](results/retrieval/dev_ablation.md).", ""]
    return out


def answers_section() -> list[str]:
    out = []
    for split in ("test", "dev"):
        rep = _load(f"answers/{split}_report.json")
        if not rep:
            continue
        out += [f"### Answers ({split} split, judged by the LLM judge + 1% numeric tolerance)", "",
                "| System | Accuracy | Precision when answering | Abstention rate | Citation precision (gold pages) | Accuracy 95% CI |",
                "|---|---|---|---|---|---|"]
        names = {"naive": "naive RAG", "best": "best (no threshold)", "oracle": "oracle (gold pages)"}
        for name in ("naive", "best", "oracle"):
            r = rep["results"].get(name)
            if not r:
                continue
            variants = [("no_threshold", names[name])]
            if "with_threshold" in r and name != "oracle":
                variants.append(("with_threshold", f"best + abstention threshold {rep['threshold']}"))
            for key, label in variants:
                o = r[key]["overall"]
                out.append(f"| {label} | {o['accuracy']} ({o['correct']}/{o['n']}) | {o['precision_when_answering']} | "
                           f"{o['abstention_rate']} | {o['citation_precision_gold_pages']} | "
                           f"{o['accuracy_ci95'][0]}-{o['accuracy_ci95'][1]} |")
        b, a = rep["results"].get("best"), rep["results"].get("best_model_arith")
        if b and a:
            bm = b["no_threshold"]["by_question_type"].get("metrics-generated")
            am = a["no_threshold"]["by_question_type"].get("metrics-generated")
            if bm and am:
                out += ["", "Numeric (metrics-generated) questions: extract-then-compute "
                        f"{bm['accuracy']} ({bm['correct']}/{bm['n']}) vs model arithmetic "
                        f"{am['accuracy']} ({am['correct']}/{am['n']})."]
        out += ["", f"{_prov(rep)}.", ""]
    return out


def other_section() -> list[str]:
    out = []
    agr = _load("answers/judge_agreement.json")
    if agr:
        j = agr["judge_plus_tolerance"]
        jr = agr["judge_raw"]
        out.append(f"- **Judge vs human labels** ({agr['n']} dev answers): {j['percent_agreement']} agreement, "
                   f"Cohen's kappa {j['cohen_kappa']} (judge alone: {jr['percent_agreement']}, kappa {jr['cohen_kappa']}).")
    pr = _load("answers/probes.json")
    if pr:
        out.append(f"- **Unanswerable probes** ({pr['best']['n']} questions about companies or periods not in the "
                   f"corpus): hallucination rate {pr['best']['hallucination_rate']} for best, "
                   f"{pr['naive']['hallucination_rate']} for naive.")
    gw = _load("answers/gateway_test_best.json")
    if gw:
        out.append(f"- **Gateway, test split, best config** ({gw['questions']} questions): model time per question "
                   f"p50 {gw['model_time_per_question_ms']['p50']} ms, p95 {gw['model_time_per_question_ms']['p95']} ms; "
                   f"cost per question {gw['cost_usd_per_question']['mean']} USD (local models).")
    cov = _load("ci/coverage.json")
    if cov:
        out.append(f"- **Tests:** rag-service {cov['rag_service']['tests']} tests, {cov['rag_service']['line_coverage_percent']}% "
                   f"line coverage; llm-gateway {cov['llm_gateway']['tests']} tests, "
                   f"{cov['llm_gateway']['line_coverage_percent']}% line coverage.")
    return (["### Other measurements", ""] + out + [""]) if out else []


def main() -> int:
    body = "\n".join(["", *retrieval_section(), *answers_section(), *other_section()])
    readme = config.REPO_ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")
    if START not in text:
        raise SystemExit("README.md has no results markers")
    text = re.sub(re.escape(START) + r".*?" + re.escape(END), lambda _: f"{START}\n{body}\n{END}", text, flags=re.S)
    readme.write_text(text, encoding="utf-8", newline="\n")
    print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
