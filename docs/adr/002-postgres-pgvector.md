# ADR 002: PostgreSQL + pgvector instead of a dedicated vector database

**Status:** accepted (2026-10-20)

**Context.** The target platform already runs PostgreSQL (and RDS supports pgvector). The corpus
is 66,727 chunks across both strategies, far below the scale where a dedicated vector database
pays for its extra operational surface.

**Decision.** One pgvector table per chunking strategy, 768-d normalized vectors, HNSW index
(`m=16`, `ef_construction=64`) on inner product, `ef_search=100`, iterative index scans for
filtered (routed) queries. Metadata filters are ordinary SQL `WHERE` clauses.

**Consequences.**
- Same database, backups, access control and monitoring as the rest of the platform; the
  gateway audit log lives in the same instance (separate schema).
- HNSW is approximate. Measured against exact search on dev queries, top-50 overlap was 0.9787
  (fixed) and 0.9637 (structure); `store.search(exact=True)` exists for checks like this.
- BM25 runs in the rag-service process (it needs the same chunk text in memory anyway), not in
  PostgreSQL full-text search, whose ranking is not BM25.
