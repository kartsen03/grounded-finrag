# ADR 008: Running the models on a 6 GB laptop GPU

**Status:** accepted (2026-10-21)

**Decision.**
- LLM: `qwen2.5:7b-instruct-q4_K_M` (4.68 GB). Of the 7-8B options it has the smallest KV
  cache per token (4 KV heads), and it follows JSON schemas well.
- Context 8192 tokens (the repair round and oracle prompts need it), flash attention and an
  8-bit KV cache.
- Ollama still offloads part of the model to the CPU on this machine (`ollama ps` showed 19-21%
  CPU at 8192 tokens and 16% even at 4096), so generation latency reflects partial offload.
- During answering, `model-server` runs on the CPU (`MODEL_DEVICE=cpu`) so the LLM gets the GPU;
  during indexing and the retrieval ablation it ran on the GPU. Each results file records which.
- Models live on drive E: (C: had about 11 GB free): a project Ollama instance on port 11435
  with `OLLAMA_MODELS=E:\ollama\models`, selected through the gateway's `OLLAMA_BASE_URL`.

**Consequences.** Timings are laptop timings; outputs at temperature 0 were not always identical
between runs, which partial CPU offload can cause.
