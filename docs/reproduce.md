# Reproducing every result

Run from `rag-service/` with its virtualenv active, unless noted. Each step writes a results file
under `results/` stamped with commit, machine, GPU, power plan and package versions.

| # | Command | Writes | Needs |
|---|---|---|---|
| 1 | `python scripts/download_financebench.py` (repo root) | `data/raw/` (gitignored) | network |
| 2 | `python scripts/make_split.py --check` (repo root) | verifies `data/splits/financebench_split_v1.json` | step 1 |
| 3 | `python -m finrag.ingest.run` | `data/processed/`, `results/ingestion/` | step 1 |
| 4 | `python -m finrag.retrieval.index` | pgvector tables, `results/indexing/` | gateway + model server |
| 5 | `python -m finrag.eval.retrieval_eval --split dev` | `results/retrieval/dev_ablation.json`, `selected.json` | step 4 |
| 6 | `python -m finrag.eval.select_retrieval --label ... --reason ...` | override recorded in `selected.json` | step 5 |
| 7 | `python -m finrag.eval.answer_runs --split dev` | `runs/answers/dev/` (gitignored) | Ollama via gateway |
| 8 | `python -m finrag.eval.answer_eval judge --split dev` | `runs/judged/dev/` | step 7 |
| 9 | `python -m finrag.eval.human_labels sheet`, label, then `... import` | `data/labels/dev_human_labels.json` | step 7 |
| 10 | `python -m finrag.eval.answer_eval agreement` | `results/answers/judge_agreement.json` | steps 8-9 |
| 11 | `python -m finrag.eval.answer_eval tune` | `results/answers/abstention_threshold.json` | step 8 |
| 12 | `python -m finrag.eval.answer_eval report --split dev` | `results/answers/dev_report.json` | step 11 |
| 13 | `python -m finrag.eval.answer_eval probes` | `results/answers/probes.json` | step 11 |
| 14 | `python -m finrag.eval.retrieval_eval --split test` (once) | `results/retrieval/test_results.json` | step 6 |
| 15 | `python -m finrag.eval.answer_runs --split test`, `answer_eval judge --split test`, `answer_eval report --split test` (once) | `results/answers/test_report.json` | step 11 |
| 16 | `python -m finrag.eval.gateway_stats --prefix test-best- --out results/answers/gateway_test_best.json` | gateway latency/cost | step 15 |
| 17 | `python -m finrag.eval.error_analysis --split dev` | `results/answers/error_analysis_dev_best.json` | step 12 |
| 18 | `python -m finrag.eval.readme_tables` | README results section | all |

Services: `docker compose up -d` (PostgreSQL, Redis); model server on :8090 (`MODEL_DEVICE=cuda`
for indexing and the retrieval ablation, `cpu` while the LLM is generating); gateway on :8080
(`OLLAMA_BASE_URL` pointing at the Ollama instance that holds the model).

Guards: test-mode scripts refuse to run twice, and the retrieval selection and abstention
threshold cannot change after the test split is scored.
