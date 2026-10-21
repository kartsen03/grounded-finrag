# Retrieval ablation (dev split)

Generated from `results/retrieval/dev_ablation.json` (values exactly as stored; hit@k = hits out of 75). Commit `e599901`, 2026-10-21T16:07:56+00:00. 75 dev questions.
Embeddings `BAAI/bge-base-en-v1.5@a5beb1e3e68b9ab74eb54cfd186867f64f240e1a`, re-ranker `BAAI/bge-reranker-base@2cfc18c9415c912f9d8155881c133215df768a70`; GPU NVIDIA GeForce RTX 3060 Laptop GPU, 6144 MiB, 592.00, power plan Turbo.

Selection rule (fixed before the run): max mrr@10, then max hit@5, then min p50 total latency (dev split). **Selected: `structure/dense/routed/norerank`**.

| Chunking | Retriever | Routing | Re-rank | hit@1 | hit@3 | hit@5 | hit@10 | MRR@10 | hit@5 95% CI | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|
| fixed | dense | no | no | 0.1200 | 0.2533 | 0.2800 | 0.4400 | 0.2122 | 0.1733-0.3867 | 54.05 | 69.73 |
| fixed | dense | no | yes | 0.1867 | 0.3733 | 0.4667 | 0.6133 | 0.3113 | 0.3467-0.5733 | 371.95 | 404.88 |
| fixed | dense | yes | no | 0.1733 | 0.3200 | 0.4533 | 0.6133 | 0.2919 | 0.3333-0.5600 | 51.91 | 66.42 |
| fixed | dense | yes | yes | 0.1733 | 0.3467 | 0.4267 | 0.6133 | 0.2932 | 0.3067-0.5333 | 384.08 | 456.71 |
| fixed | bm25 | no | no | 0.1067 | 0.1733 | 0.2000 | 0.2400 | 0.1510 | 0.1200-0.2933 | 0.98 | 1.46 |
| fixed | bm25 | no | yes | 0.1733 | 0.2667 | 0.3467 | 0.4000 | 0.2413 | 0.2400-0.4533 | 350.14 | 380.66 |
| fixed | bm25 | yes | no | 0.1600 | 0.2267 | 0.3067 | 0.4933 | 0.2372 | 0.2000-0.4133 | 2.99 | 4.76 |
| fixed | bm25 | yes | yes | 0.1600 | 0.3467 | 0.3733 | 0.5467 | 0.2718 | 0.2667-0.4800 | 359.76 | 413.59 |
| fixed | hybrid | no | no | 0.1200 | 0.2400 | 0.3600 | 0.4800 | 0.2168 | 0.2533-0.4667 | 53.15 | 63.51 |
| fixed | hybrid | no | yes | 0.1867 | 0.3467 | 0.4533 | 0.6133 | 0.2953 | 0.3467-0.5600 | 389.69 | 426.67 |
| fixed | hybrid | yes | no | 0.1733 | 0.3867 | 0.5333 | 0.6667 | 0.3177 | 0.4133-0.6400 | 51.04 | 62.28 |
| fixed | hybrid | yes | yes | 0.1467 | 0.3467 | 0.3867 | 0.5333 | 0.2623 | 0.2800-0.4933 | 397.79 | 475.92 |
| structure | dense | no | no | 0.2000 | 0.3067 | 0.3600 | 0.6133 | 0.2925 | 0.2533-0.4667 | 50.9 | 63.65 |
| structure | dense | no | yes | 0.1867 | 0.3733 | 0.5200 | 0.6667 | 0.3245 | 0.4000-0.6267 | 367.83 | 470.26 |
| structure | dense | yes | no **(selected)** | 0.2667 | 0.4267 | 0.5467 | 0.7333 | 0.3818 | 0.4400-0.6533 | 50.12 | 71.82 |
| structure | dense | yes | yes | 0.1333 | 0.3333 | 0.4267 | 0.6400 | 0.2753 | 0.3067-0.5333 | 369.96 | 499.71 |
| structure | bm25 | no | no | 0.0800 | 0.1867 | 0.2133 | 0.2933 | 0.1439 | 0.1200-0.3067 | 1.0 | 2.06 |
| structure | bm25 | no | yes | 0.1600 | 0.2400 | 0.2933 | 0.3733 | 0.2177 | 0.1867-0.4000 | 325.88 | 397.28 |
| structure | bm25 | yes | no | 0.1733 | 0.2933 | 0.4000 | 0.5333 | 0.2690 | 0.2933-0.5067 | 2.65 | 4.78 |
| structure | bm25 | yes | yes | 0.1333 | 0.4000 | 0.4800 | 0.6400 | 0.2876 | 0.3733-0.5867 | 333.54 | 374.11 |
| structure | hybrid | no | no | 0.1867 | 0.3067 | 0.4267 | 0.4933 | 0.2745 | 0.3200-0.5333 | 50.1 | 67.02 |
| structure | hybrid | no | yes | 0.1733 | 0.3733 | 0.5200 | 0.7067 | 0.3214 | 0.4133-0.6267 | 369.69 | 440.51 |
| structure | hybrid | yes | no | 0.2400 | 0.4533 | 0.6133 | 0.7067 | 0.3798 | 0.4933-0.7200 | 54.26 | 68.25 |
| structure | hybrid | yes | yes | 0.1467 | 0.3333 | 0.5067 | 0.6400 | 0.2865 | 0.3867-0.6133 | 379.07 | 456.85 |

## Per-stage latency of the selected configuration (ms)

| Stage | p50 | p95 |
|---|---|---|
| dense_search | 9.99 | 19.28 |
| embed_query | 39.34 | 55.98 |
| route | 0.38 | 0.99 |
| total | 50.12 | 71.82 |

Routing applied a filter to 72 of 75 questions; the gold document was inside the filter for 72 of them.

HNSW vs exact search, unfiltered dense top-50 overlap: {'recall@50': {'fixed': 0.9787, 'structure': 0.9637}}
