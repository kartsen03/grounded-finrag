# grounded-finrag

Question answering over financial filings (10-K, 10-Q, 8-K, earnings releases) where every
answer cites `[document, page]`, numeric answers are computed in Python from cited line items,
and every model call goes through a Spring Boot LLM gateway. Evaluated on a fixed dev/test
split of the FinanceBench open-source sample.

> **Status: in progress.** Results tables are added only after the runs that produce them;
> each result records the model, hardware and commit it came from.

**Non-commercial project.** Code: PolyForm Noncommercial 1.0.0 (`LICENSE`). Evaluation data:
FinanceBench, CC BY-NC 4.0 (`NOTICE.md`). No FinanceBench files are committed to this repo.

## Data

```bash
python scripts/download_financebench.py   # pinned upstream commit, SHA-256 verified
python scripts/make_split.py --check      # verifies the committed dev/test split
```

The download is the 150 open-source questions plus the 84 PDFs they reference. The split
(`data/splits/financebench_split_v1.json`) is seeded and stratified by question type:
75 dev questions for every design decision, 75 test questions scored once per final
configuration.

## Local infrastructure

```bash
docker compose up -d   # PostgreSQL 17 + pgvector, Redis 7.2, bound to 127.0.0.1
```
