# ADR 004: Evaluation protocol: fixed split, page-level metrics, decisions on dev, test once

**Status:** accepted (2026-10-20)

**Decision.**
- **Split:** 75 dev / 75 test, stratified by question type, seed 20261020, committed as IDs
  (`data/splits/financebench_split_v1.json`). 18 documents appear in both halves; nothing is
  tuned per document.
- **Retrieval metric:** evidence-page hit@1/3/5/10 and MRR@10 over the ranked list of unique
  (document, page) pairs, using each chunk's primary page, so fixed and structure chunks are
  compared fairly. 95% bootstrap CIs (2,000 resamples).
- **Selection:** the rule (MRR@10, then hit@5, then p50 latency) was fixed in code before the
  first dev run. It picked dense + routing. On review, the final choice was hybrid + routing,
  because the answer step reads the top 5 chunks and hit@5 was 0.6133 vs 0.5467 (MRR@10 0.3798
  vs 0.3818). This override is recorded in `results/retrieval/selected.json` with both
  configurations' dev metrics; the CIs overlap, and the test set had not been scored.
- **Test:** scripts refuse to score the test split twice and refuse to change the selection or
  the abstention threshold after test is scored.

**Consequences.** Dev numbers guide design; test numbers are reported once, with their CIs, for
the naive baseline and the final configuration.
