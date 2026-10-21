# ADR 005: No cross-encoder re-ranking in the final retrieval configuration

**Status:** accepted (2026-10-21)

**Context.** Re-ranking is the textbook last stage of a retrieval pipeline. In the dev ablation,
bge-reranker-base improved unrouted retrieval (structure + dense: MRR@10 0.2925 -> 0.3245) but
hurt routed retrieval (0.3818 -> 0.2753), and it added about 320 ms p50 on the GPU.

**Diagnosis** (`results/retrieval/dev_rerank_diagnosis.json`). It was not demoting tables in
general: the share of tables in the top 5 went from 0.392 to 0.4373. Once routing limits the
candidates to one filing, the re-ranker trades the gold table for similar tables from the same
filing. On metrics questions it dropped the gold page from the top 5 eleven times and added it
four times.

**Decision.** No re-ranking in the final configuration. The cross-encoder is still used, as the
abstention support score: how relevant the best retrieved source is.

**What could change this:** a re-ranker fine-tuned on financial tables, table-aware rendering
(column headers repeated into each row), or re-ranking a larger, unrouted pool.
