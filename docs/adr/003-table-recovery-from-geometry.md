# ADR 003: Recover tables from word geometry with pdfplumber

**Status:** accepted (2026-10-20)

**Context.** Most FinanceBench answers live in financial statement tables. Flattened text loses
the row-column structure (which number belongs to which year). Options considered:
- PyMuPDF `find_tables`: fast, but AGPL-licensed, which conflicts with distributing this
  repository under a non-commercial license.
- Docling (layout and table models): high quality, but slow and heavy for 12,013 pages on a laptop
  within a two-day build.
- pdfplumber's built-in table finder: relies on ruling lines; on these statements it returned
  one-row fragments.

**Decision.** pdfplumber (MIT) for positioned words, plus our own table recovery: rows are labels
followed by numeric cells, columns are unions of overlapping numeric-cell spans, year rows and
lines above become headers. Rendered as Markdown. Every text repair is logged as a parse issue.

**Consequences.**
- All 189 gold evidence items are found on their labeled page in our parsed text (187 strong
  matches; the other 2 are upstream evidence strings with spaces removed).
- Known defects are documented in `docs/ingestion.md`: title lines absorbed into headers,
  two-column layouts read across, rotated text dropped.
- Parsing takes 728.4 s of wall time on 10 CPU processes for the corpus.
