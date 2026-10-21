# Retrieval ablation (dev split)

Generated from `results/retrieval/dev_ablation.json`. Commit `e599901`, 2026-10-21T16:07:56+00:00. 75 dev questions.
Embeddings `BAAI/bge-base-en-v1.5@a5beb1e3e68b9ab74eb54cfd186867f64f240e1a`, re-ranker `BAAI/bge-reranker-base@2cfc18c9415c912f9d8155881c133215df768a70`; GPU NVIDIA GeForce RTX 3060 Laptop GPU, 6144 MiB, 592.00, power plan Turbo.

Selection rule (fixed before the run): max mrr@10, then max hit@5, then min p50 total latency (dev split). **Selected: `structure/dense/routed/norerank`**.

| Chunking | Retriever | Routing | Re-rank | hit@1 | hit@3 | hit@5 | hit@10 | MRR@10 | hit@5 95% CI | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|
| fixed | dense | no | no | 0.120 | 0.253 | 0.280 | 0.440 | 0.212 | 0.173-0.387 | 54 | 70 |
| fixed | dense | no | yes | 0.187 | 0.373 | 0.467 | 0.613 | 0.311 | 0.347-0.573 | 372 | 405 |
| fixed | dense | yes | no | 0.173 | 0.320 | 0.453 | 0.613 | 0.292 | 0.333-0.560 | 52 | 66 |
| fixed | dense | yes | yes | 0.173 | 0.347 | 0.427 | 0.613 | 0.293 | 0.307-0.533 | 384 | 457 |
| fixed | bm25 | no | no | 0.107 | 0.173 | 0.200 | 0.240 | 0.151 | 0.120-0.293 | 1 | 1 |
| fixed | bm25 | no | yes | 0.173 | 0.267 | 0.347 | 0.400 | 0.241 | 0.240-0.453 | 350 | 381 |
| fixed | bm25 | yes | no | 0.160 | 0.227 | 0.307 | 0.493 | 0.237 | 0.200-0.413 | 3 | 5 |
| fixed | bm25 | yes | yes | 0.160 | 0.347 | 0.373 | 0.547 | 0.272 | 0.267-0.480 | 360 | 414 |
| fixed | hybrid | no | no | 0.120 | 0.240 | 0.360 | 0.480 | 0.217 | 0.253-0.467 | 53 | 64 |
| fixed | hybrid | no | yes | 0.187 | 0.347 | 0.453 | 0.613 | 0.295 | 0.347-0.560 | 390 | 427 |
| fixed | hybrid | yes | no | 0.173 | 0.387 | 0.533 | 0.667 | 0.318 | 0.413-0.640 | 51 | 62 |
| fixed | hybrid | yes | yes | 0.147 | 0.347 | 0.387 | 0.533 | 0.262 | 0.280-0.493 | 398 | 476 |
| structure | dense | no | no | 0.200 | 0.307 | 0.360 | 0.613 | 0.292 | 0.253-0.467 | 51 | 64 |
| structure | dense | no | yes | 0.187 | 0.373 | 0.520 | 0.667 | 0.325 | 0.400-0.627 | 368 | 470 |
| structure | dense | yes | no **(selected)** | 0.267 | 0.427 | 0.547 | 0.733 | 0.382 | 0.440-0.653 | 50 | 72 |
| structure | dense | yes | yes | 0.133 | 0.333 | 0.427 | 0.640 | 0.275 | 0.307-0.533 | 370 | 500 |
| structure | bm25 | no | no | 0.080 | 0.187 | 0.213 | 0.293 | 0.144 | 0.120-0.307 | 1 | 2 |
| structure | bm25 | no | yes | 0.160 | 0.240 | 0.293 | 0.373 | 0.218 | 0.187-0.400 | 326 | 397 |
| structure | bm25 | yes | no | 0.173 | 0.293 | 0.400 | 0.533 | 0.269 | 0.293-0.507 | 3 | 5 |
| structure | bm25 | yes | yes | 0.133 | 0.400 | 0.480 | 0.640 | 0.288 | 0.373-0.587 | 334 | 374 |
| structure | hybrid | no | no | 0.187 | 0.307 | 0.427 | 0.493 | 0.275 | 0.320-0.533 | 50 | 67 |
| structure | hybrid | no | yes | 0.173 | 0.373 | 0.520 | 0.707 | 0.321 | 0.413-0.627 | 370 | 441 |
| structure | hybrid | yes | no | 0.240 | 0.453 | 0.613 | 0.707 | 0.380 | 0.493-0.720 | 54 | 68 |
| structure | hybrid | yes | yes | 0.147 | 0.333 | 0.507 | 0.640 | 0.286 | 0.387-0.613 | 379 | 457 |

## Per-stage latency of the selected configuration (ms)

| Stage | p50 | p95 |
|---|---|---|
| dense_search | 10.0 | 19.3 |
| embed_query | 39.3 | 56.0 |
| route | 0.4 | 1.0 |
| total | 50.1 | 71.8 |

Routing applied a filter to 72 of 75 questions; the gold document was inside the filter for 72 of them.

HNSW vs exact search, unfiltered dense top-50 overlap: {'recall@50': {'fixed': 0.9787, 'structure': 0.9637}}
