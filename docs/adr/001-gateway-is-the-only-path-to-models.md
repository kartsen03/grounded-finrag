# ADR 001: The gateway is the only path to any model, including embeddings and the re-ranker

**Status:** accepted (2026-10-20)

**Context.** The brief makes the LLM gateway the only path to any model, and also asks for a
local BGE embedding model and a local cross-encoder re-ranker. Ollama serves the LLM and can
serve embeddings, but has no cross-encoder re-ranking.

**Decision.** The gateway exposes `/v1/chat/completions`, `/v1/embeddings` and `/v1/rerank`.
Chat routes to Ollama; embeddings and re-ranking route to `model-server/`, a small FastAPI
service running sentence-transformers. The model server binds to 127.0.0.1 and only the
gateway calls it.

**Consequences.**
- Every model call gets the same authentication, rate limits, caching, accounting and audit.
  Indexing traffic is visible in the audit log like answering traffic.
- Moving to AWS is a configuration change: the same three endpoints map to Bedrock chat,
  embedding and rerank models (see `docs/aws-deployment.md`).
- Cost: one more service and an extra HTTP hop per call. Query embedding through the gateway
  measured a p50 of 39.34 ms on the GPU (`results/retrieval/dev_ablation.json`, selected
  configuration).
- A bug found because of the extra hop: the JDK HTTP client's HTTP/2 upgrade lost request
  bodies at uvicorn; upstream calls are pinned to HTTP/1.1 (regression test included).
