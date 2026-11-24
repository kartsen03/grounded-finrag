# Commit map (history edit of 2026-11-24)

On 2026-11-24 the commit messages on `main` were edited (trailer lines removed) and the branch was
force-pushed. File contents did not change: every rewritten commit has the same tree, author, and
timestamps as the commit it replaces (checked pair by pair before the push).

Result files under `results/` and some docs record the commit a run was made from, in the old
hashes. They are left as recorded. Use this table to find the matching commit in the current history.
A row marked "yes" is referenced by at least one tracked file.

| old | new | referenced | subject |
|---|---|---|---|
| `235077d` | `9a60cb9` |  | Scaffold repository as a non-commercial project |
| `053aa70` | `fe703d2` |  | Add docker-compose for PostgreSQL + pgvector and Redis |
| `f63d497` | `fec160d` |  | Add pinned FinanceBench downloader with SHA-256 manifest |
| `0d1988c` | `beca680` |  | Add seeded dev/test split stratified by question type |
| `8b0097e` | `46c1c2d` |  | Write generated JSON files with LF line endings |
| `21e18a8` | `b8352c4` |  | Pin infrastructure images by digest |
| `8eef3ab` | `2d3db9f` |  | Add rag-service package with corpus metadata and provenance |
| `b2d59c5` | `d2fddb0` |  | Parse filing PDFs into heading, text and Markdown table blocks |
| `29b1fab` | `33d0cbb` |  | Add fixed-size and page/section-aware chunking |
| `6b58e6a` | `12c8436` |  | Add parallel ingestion runner and evidence-page check |
| `7a50e4b` | `525aca5` |  | Add local model server for BGE embeddings and re-ranking |
| `c859fe4` | `785b998` |  | Add Spring Boot LLM gateway skeleton |
| `17cf8e0` | `f31631a` |  | Merge wrapped table labels that continue with an amount |
| `0859f68` | `ae5f97a` |  | Parse 8-K filing dates with either separator |
| `2bd943f` | `a6f5feb` |  | Force HTTP/1.1 for upstream provider calls |
| `0c2d219` | `4f2a6bb` |  | Add retrieval: pgvector dense, BM25, RRF, routing and re-ranking |
| `90fd681` | `0580127` |  | Add retrieval ablation harness with a pre-registered selection rule |
| `643544a` | `7369b6d` |  | Add rag-service FastAPI app and record git state at run start |
| `cfa3d78` | `80b9938` |  | Generate Markdown result tables from results JSON |
| `2f46fa1` | `85eeddb` |  | Record ingestion results for the full corpus |
| `bf2efcb` | `155f972` |  | Document ingestion: table recovery, evidence-page check, parse-issue log |
| `ea1d08b` | `8859162` | yes | Strip control characters from PDF text and log them |
| `e599901` | `841567c` | yes | Record ingestion and indexing results at ea1d08b |
| `1e49f37` | `7c9db1c` | yes | Add dev-only diagnosis of re-ranking on routed queries |
| `d4cd1ec` | `3fdb56e` |  | Record dev retrieval ablation (24 configurations) and selection |
| `c2eddae` | `f09750f` |  | Print result tables with the stored precision, no extra rounding |
| `450a8cb` | `8001e94` | yes | Add a recorded override for the retrieval selection (dev only) |
| `b77c233` | `8831e58` |  | Select hybrid + routing (structure chunks, no re-rank) for the final config |
| `d9dc8fe` | `4b16f7c` |  | Add grounded answering with citation verification and extract-then-compute |
| `fabe0ac` | `0be19e9` |  | Accept bracketed source IDs, cap answer length, add answer runner |
| `d919b78` | `181ef7b` |  | Add LLM judge, rubric, human-label tooling and unanswerable probes |
| `f4906d2` | `d0f04d0` |  | Add answer evaluation: judge runs, agreement, threshold, probes, reports |
| `36db9c7` | `1dfd40f` |  | Redact secrets and personal data from every gateway log line |
| `e0158bd` | `0aa74b4` |  | Add gateway resilience, rate limiting, caching, accounting and audit |
| `ffd9cfa` | `dadbb16` | yes | Add CPU retrieval regression gate on a synthetic fixture corpus |
| `3caf80b` | `5f775fe` |  | Record CI retrieval gate baseline (CPU): hit@5 1.0, MRR@10 0.9167 |
| `5af11fa` | `f1ec7d5` |  | Add CI, retrieval gate job, CodeQL, dependency scanning and Dependabot |
| `52b42ec` | `11eab61` |  | Document architecture, decision records and AWS deployment design |
| `3f427c4` | `c1fad78` |  | Add /answer endpoint with the final configuration and dev-tuned threshold |
| `4fa8c2f` | `38f4586` |  | Fix grounded-mode over-abstention: generate claims before the flag |
| `a1da99d` | `89d5953` |  | Add per-question latency, token and cost stats from the gateway audit log |
| `3a3ba5b` | `e5a0759` |  | Record gateway cache hits per answer |
| `6b6ac5e` | `cfd952b` |  | Rewrite README around generated results tables |
| `87e829c` | `5df09f1` |  | Containerize the services behind a compose profile |
| `0525590` | `4967df5` |  | Test the answer pipeline's repair, abstention and extract paths |
| `cd8bafe` | `100cf47` |  | Add rule-based failure taxonomy for judged answers |
| `c8ed144` | `e52e23f` |  | Document the command sequence that reproduces every result |
| `681799f` | `188edf1` |  | Add minimal Streamlit demo UI (stretch) |
| `116b93d` | `f09bf35` |  | Count probe hallucinations only when an answer commits to a value |
| `39c6675` | `489d4eb` | yes | Record dev answer report, abstention threshold and probe results |
| `013086e` | `b02d725` |  | Score retrieval on the test split (once) |
| `da4f41a` | `ec65c40` |  | Refine failure taxonomy rules and record dev error analysis |
| `81c736f` | `0d49f79` |  | Do not match figures starting inside another number |
| `5cb5f95` | `af92acd` | yes | Fix the figure regex lookbehind (a shell edit dropped a backslash) |
| `840e027` | `6c49cda` |  | Re-record dev error analysis for all configurations at a clean commit |
| `f4ca64f` | `e8f4a79` |  | Write dev error analysis with a failure taxonomy and real examples |
| `0acfbc6` | `84ec19b` |  | Add a script that records both services' test counts and coverage |
| `af70766` | `d5ed13a` |  | Count Python tests from JUnit XML in the coverage script |
| `ff551fb` | `22507ef` |  | Record test counts and coverage for both services |
| `fb29b55` | `d3adadf` |  | Add design-choices log with checkpoints 1-3 for later review |
| `77956fc` | `83431f0` |  | Show test retrieval results and dev answer results in the README |
| `06b063a` | `f646d64` | yes | Run a normal Maven verify in the coverage script |
| `ac8ca09` | `9a70e06` | yes | Record per-question latency, tokens and cost for test best from the audit log |
| `c7d0ec4` | `da8ac99` |  | Add hand labels and judge-human agreement; make the scoring verdict a recorded choice |
| `8f38138` | `ed399de` | yes | Score answers with the raw judge verdict (chosen on dev, before test) |
| `57a0a5d` | `2cce3ae` | yes | Re-tune the threshold and re-score dev with the raw judge verdict |
| `69d0f40` | `545c233` | yes | Score answers on the test split (once) |
| `2a8671d` | `fed63f9` |  | Re-run unanswerable probes with the final (raw-judge) threshold |
| `d18c116` | `abe7efa` | yes | Mark the Maven wrapper executable |
| `a776f8b` | `eed22b7` |  | Fix vulnerable dependencies reported by OSV-Scanner and pip-audit |
| `4b08837` | `6737f34` |  | Update README with test answer results, judge agreement and an honest reading |
| `5a5812d` | `e23899e` |  | Log judge validation, test results and security findings in choices.md |
| `b5e0652` | `7dafa9e` |  | Accept the remaining torch advisory with a reason; raise the setuptools build floor |
| `92e9249` | `e8f59ee` | yes | Upgrade pdfplumber to 0.11.10 (pdfminer.six 20260107) after checking identical output |
| `6dfbae0` | `d675426` |  | Re-record coverage at the final code state (rag-service 42 tests, 45.8%) |
| `0bac4fd` | `3da952a` |  | Create the pgvector extension before registering its type |
| `02201cb` | `e3cc799` |  | Pin a setuptools floor for the model server and accept PYSEC-2026-3447 |
| `2bfc4b9` | `5306afd` |  | Pin setuptools exactly for the model server |
| `bef4f3f` | `6fb5530` |  | Allow an explicit document filter in retrieval and answering |
| `1a3c746` | `4d59040` |  | Add an mcp-server client to the gateway |
| `cf3fe23` | `8dcbe49` |  | Add an MCP server exposing read-only filing tools |
