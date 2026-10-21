# Design choices and open discussion questions

A running log for a later review chat. Each entry: what was decided, why, the evidence,
and questions to discuss. Numbers come from committed results files.

## Checkpoint 1: retrieval (Steps 1-3)

### Chunking
- **Choice:** two strategies compared. *fixed* = 350-token windows, 50-token overlap. *structure* = whole
  blocks of one page, tables kept intact.
- **Evidence:** structure beat fixed in every comparable row of `results/retrieval/dev_ablation.md`.
  44.38% of fixed chunks span two pages.

### Embeddings
- **Choice:** bge-base-en-v1.5 (768-d), served by `model-server/` behind the gateway. Stored in pgvector
  with an HNSW index.
- **Evidence:** HNSW recall@50 vs exact search: 0.9787 for fixed, 0.9637 for structure.

### BM25 vs dense, and RRF
- **Choice:** BM25 matches words; dense matches meaning. RRF fuses the two by rank only:
  1/(60+rank).
- **Evidence:** BM25 alone was weakest (fixed, unrouted: hit@5 15/75). Hybrid with routing had the best
  hit@5 (46/75).

### Metadata routing
- **Choice:** detect company and fiscal year/quarter. Fallback chain: same year, then next year's filing,
  then the whole company.
- **Evidence:** filtered 72 of 75 dev questions; the gold document was kept all 72 times. This was the
  biggest single gain.

### Re-ranking (cross-encoder bge-reranker-base)
- **Choice:** not used in the final configuration.
- **Evidence:** it helped without routing and hurt with routing. The diagnosis
  (`results/retrieval/dev_rerank_diagnosis.json`) shows it swaps the gold table for similar tables from
  the same filing; on metrics questions it lost the gold page 11 times and gained it 4 times. It adds
  about 320 ms p50.

### Final retrieval selection
- **Choice:** structure chunks / hybrid / routed / no re-rank.
- **Why:** the pre-registered rule picked dense (MRR@10 0.3818 vs 0.3798). It was overridden on dev
  because answers read the top 5 chunks: hit@5 is 0.6133 for hybrid vs 0.5467 for dense. The confidence
  intervals overlap. Recorded in `results/retrieval/selected.json`; the test set was untouched.

### Questions to discuss
1. Why score retrieval by unique pages instead of chunks? What would go wrong comparing fixed vs
   structure on chunk-level hit@k?
2. Was overriding the pre-registered rule justified? How do you phrase it honestly in an interview?
3. Why might a web-trained cross-encoder fail to pick the right table among a 10-K's many similar
   tables? What could fix it (fine-tuning, table-aware text, a larger re-rank pool)?

## Checkpoint 2: answering and answer evaluation (Steps 4-5)

Numbers are dev split unless marked; correctness is the LLM judge (validation against 40 hand labels
pending). Sources: `results/answers/dev_report.json`, `abstention_threshold.json`, `probes.json`,
`error_analysis_dev_*.json`.

### Citation verification
- **Choice:** sources are shown as [S1]..[S5]; the model returns JSON claims with source IDs. An ID
  that was not provided, or a claim with no ID, fails; one repair round, then abstain. IDs are mapped
  back to [document, page] in Python. Numbers not printed on the cited pages are flagged.
- **Why:** a fabricated citation becomes detectable, and displayed citations are always exact.
- **Evidence:** best config, gold-page citation precision 0.4412. The JPMorgan Q2 2022 example
  (`financebench_id_00394`) cited the gold page and still drew the wrong conclusion: "points to a
  retrieved page" is not "supports the claim".

### Abstention
- **Choice:** two triggers: the model's insufficient-evidence flag, and a support score (best
  cross-encoder relevance among the sources) below a threshold tuned on dev. Rule fixed before tuning:
  maximize correct minus incorrect answers.
- **Evidence:** the rule chose 0.9962: precision when answering 0.4419 -> 0.7778, coverage 0.12.
  Probes: best abstained on 30/30; naive committed to an answer on 2/30 (lenient classifier, lower
  bound). A dev bug fixed: asking for the flag first in the JSON schema made the model abstain in 14
  of 19 grounded answers that had the gold page.

### Extract-then-compute
- **Choice:** for numeric questions the model returns cited line items plus a formula; Python checks
  every value against its cited page and evaluates the formula (only + - * / and parentheses).
- **Evidence:** caught hallucinated inputs (Block current liabilities 516,426 vs 577,464 printed).
  It did not beat model arithmetic on numeric dev questions: 8/25 vs 9/25. Remaining errors are
  formula and metric-definition choices (Corning DPO; average margin vs margin of totals).

### Judge validation
- **Choice:** same 7B model as judge, reference-based, written rubric (`docs/judge_rubric.md`), 1%
  numeric tolerance enforced in Python. 40 dev answers (10 per configuration, seeded, blind) hand-
  labeled; report percent agreement and Cohen's kappa with and without the tolerance check.
- **Evidence so far:** reading failures suggests false negatives ("Las Vegas Strip Resorts",
  "$1,824 million" vs "$1.8 bn"). Agreement numbers come after labeling.

### Dev summary
naive 14/75, best 19/75 (abstention 0.4267), best with model arithmetic 20/75, oracle 33/75.
Retrieval misses are the largest bucket: 28 of best's 56 failures; 24 of those 28 had the right
filing (page ranking, not routing).

### Questions to discuss
1. Why can't "every citation points to a retrieved page" catch the JPMorgan error, and what check would?
2. The threshold maximizes correct minus wrong. When would you choose another point on the curve,
   and who should decide that at an asset manager?
3. Extract-then-compute did not win on dev. Is it still worth keeping, and how would you argue it?

## Checkpoint 3: the LLM gateway (Step 6)

### Why a gateway
- **Choice:** every model call (chat, embeddings, re-ranking) goes through one Spring Boot service.
- **Why:** one place for auth, rate limits, caching, retries and fallback, cost accounting and audit;
  switching providers (e.g. Bedrock) is configuration, not application code. See ADR 001 and 007.

### Layers (llm-gateway/src/main/java/dev/finrag/gateway/)
- Filters: RequestIdFilter -> ApiKeyFilter (SHA-256, constant-time compare) -> RateLimitFilter
  (Redis fixed window, atomic Lua INCR+EXPIRE, 429 with Retry-After, rejections audited).
- ModelController: /v1/chat/completions, /v1/embeddings, /v1/rerank with validation.
- GatewayService: cache lookup -> routes in order -> accounting -> one audit row per request.
- ResilientCaller: Resilience4j retry around a circuit breaker per provider; only timeouts, 429 and
  5xx are retried or counted; open circuit -> immediate fallback.
- ModelRouter / ProviderRegistry: alias -> primary + fallbacks; hosted fallback only with an API key.
- Providers: Ollama, model server, OpenAI-compatible; pinned to HTTP/1.1 (HTTP/2 upgrade lost bodies).
- UsageAccounting: Micrometer request/token/cost counters and latency timers (/actuator/prometheus).
- AuditLog + V1__audit_log.sql: triggers block UPDATE/DELETE/TRUNCATE; hash chain under an advisory
  lock; redacted 160-char preview, never full prompts.
- Redactor + logback-spring.xml: every log line masked (keys, tokens, emails, phones, SSNs, Luhn cards).
- **Evidence:** 20 JUnit tests pass, 71.95% line coverage (`results/ci/coverage.json`), real Redis and
  PostgreSQL via Testcontainers, intact chain after 40 concurrent inserts.

### Questions to discuss
1. Why does the breaker count only retryable failures? What breaks if a 400 opens it?
2. Triggers block UPDATE/DELETE and rows are hash-chained: what does each protect against that the
   other does not?
3. Rate limiting fails open when Redis is down. When would fail-closed be the right policy?
