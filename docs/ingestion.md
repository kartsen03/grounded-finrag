# Ingestion: parsing, tables, chunking and the parse-issue log

Numbers here come from `results/ingestion/summary.json` and
`results/ingestion/evidence_page_check.json` (full corpus run, RTX 3060 laptop, CPU-only
step, 10 worker processes). Regenerate with `python -m finrag.ingest.run`.

## What the parser produces

Each PDF page becomes an ordered list of blocks: `heading`, `text` or `table`. Page indexes
are 0-based, the same convention as FinanceBench's `evidence_page_num`. Each block records
the 10-K/10-Q section (`Item 7. ...`) and nearest sub-heading in effect at that point.

Corpus: 84 documents, 12,013 pages, 26,006 heading blocks, 91,397 text blocks and 7,129
tables rendered as Markdown. Wall time 696.2 s.

### Tables from geometry

Financial statements in these PDFs rarely have ruling lines, and pdfplumber's line-based
table finder split them into one-row fragments. The parser therefore rebuilds tables from
word positions (`ingest/layout.py`, `ingest/tables.py`):

1. A line is split into cells wherever the gap between words is wider than a space.
2. A *row* is a label followed by numeric cells (`1,577`, `(370)`, `5.5%`, dashes).
3. Rows plus short label lines between them ("Net revenue:") form a table block.
4. Columns are unions of overlapping numeric-cell spans (right-aligned numbers, centered
   dashes and left-aligned numbers all land in the right column).
5. Year rows and lines above the block become the header.

Example (3M FY2018 cash flow statement, page index 59):

```
| (Millions) | 2018 | 2017 | 2016 |
|---|---|---|---|
| Net income including noncontrolling interest | 5,363 | 4,869 | 5,058 |
| Purchases of property, plant and equipment (PP&E) | (1,577) | (1,373) | (1,420) |
```

### Checking our pages against the gold labels

For each of the 189 evidence items, the evidence text was compared with parsed pages
p-1, p and p+1. 187 matched best at p (median word coverage 1.0), none matched better at
an adjacent page, and 2 were weak. Both weak cases are FinanceBench's own evidence text
with the spaces removed (`Cashandcashequivalents`, `CONSOLIDATEDBALANCESHEETS`); our parsed
table for those pages is correct. Conclusion: the 0-based page convention holds, and hit@k
can be computed directly on `page_idx`.

## Parse-issue log

Every repair or suspicious page is written to `data/processed/parse_issues.jsonl`
(gitignored; counts and examples are committed in the summary).

| Issue | Count | Documents | What it is | Handling |
|---|---|---|---|---|
| split_word_joined | 384 | 52 | Kerning gaps split words: `OVERVI EW`, `Incom e`, `Hedge s` | Joined only if one side is a fragment and the joined word occurs elsewhere in the same document; each join logged with its gap |
| dehyphenated | 50 | 33 | Line-end hyphenation: `non- current` | Joined only when the joined word occurs elsewhere in the document, otherwise the hyphen is kept. Trade-off: `pre-tax` became `pretax` because both spellings appear |
| low_text_page | 187 | 45 | Pages with under 200 characters: image-only charts, covers, blank pages | Logged. No gold evidence page is in this set |
| table_of_contents_page | 160 | 71 | Pages with four or more `Item N.` lines | Section tracking skipped so a TOC cannot set the current section |
| rotated_text | 4 | 4 | Non-upright words (JPMorgan rotated table labels) | Rotated words dropped; one gold evidence page is affected |
| unmapped_cid_glyphs | 3 | 3 | `(cid:N)` glyphs with no Unicode mapping | Logged |

Defects found by inspection but not repaired:
- **Title lines absorbed into a table header.** On Corning's FY2020 balance sheet the
  right-aligned "Corning Incorporated and Subsidiary Companies" line overlaps the number
  columns, so it ends up in the column headers.
- **Unmapped dashes and apostrophes (U+FFFD).** Resolved by context: attached to a letter
  -> apostrophe, free-standing -> em dash.
- **Two-column layouts** in some earnings releases are read line by line across both
  columns.

## Chunking strategies

Both strategies prepend the same metadata header (company, form, period, section) to the
text that is embedded, so the comparison isolates where chunks begin and end.

| | fixed | structure |
|---|---|---|
| Rule | 350-token windows, 50-token overlap, across the whole document | whole blocks of one page, packed up to 350 tokens; headings stay with what follows; oversized tables split by rows with the header repeated |
| Chunks | 29,699 | 37,028 |
| Tokens p50 / p95 / max | 350 / 350 / 352 | 269 / 341 / 474 |
| Chunks containing a table | 33.55% | 22.87% |
| Chunks spanning two pages | 44.38% | 0% |

Tokens are counted with the embedding model's tokenizer (bge-base-en-v1.5, pinned revision).
The structure maximum (474) comes from a heading carried into the next chunk together with a
block that already filled the budget; it is still under the model's 512-token limit.
