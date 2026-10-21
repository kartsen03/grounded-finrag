# Error analysis (dev split)

Counts come from `results/answers/error_analysis_dev_<config>.json` (commit 5cb5f95), produced
by the rule-based taxonomy in `rag-service/src/finrag/eval/error_analysis.py`. Every incorrect
or abstained answer gets the first matching category. Correctness is the LLM judge's verdict
with the 1% numeric tolerance, before any abstention threshold. **Caveat:** the judge is still
being validated against hand labels, and several "other" failures below look like judge false
negatives.

| Category | naive | best | best + model arithmetic | oracle |
|---|---|---|---|---|
| retrieval_miss | 49 | 28 | 27 | 0 |
| table_parse_error | 0 | 0 | 0 | 0 |
| wrong_period | 0 | 0 | 0 | 1 |
| arithmetic | 4 | 5 | 8 | 12 |
| unsupported_claim | 0 | 2 | 2 | 3 |
| abstained_despite_gold_page | 0 | 13 | 6 | 19 |
| other | 8 | 8 | 12 | 7 |
| **failures (of 75)** | **61** | **56** | **55** | **42** |

What the table says:
- **Retrieval is the main bottleneck.** For best, 28 of 56 failures had no gold page among the
  5 sources. In 24 of those 28, routing had already picked the right filing: the miss is page
  ranking inside the right document, not finding the document. Naive retrieval misses 49.
- **With perfect retrieval (oracle), the remaining errors move to extraction and arithmetic
  (12) and to abstention (19).** Abstentions with the gold page present include verification
  rejecting values the model did not copy correctly, so they are often caught hallucinations,
  not lost answers.
- **The automated rules confirmed no table parse error among dev failures.** Two first versions
  of the rule produced false positives (printed page numbers, which the parser strips on
  purpose, and dates glued together in FinanceBench's own evidence text); both were fixed
  before these counts. A real parse defect does appear inside the oracle's wrong-period case
  below.

## Examples, one per failure type

### Retrieval miss: vocabulary mismatch inside the right filing
`financebench_id_03029`, best. The question asks for 3M's FY2018 "capital expenditure" from the
cash flow statement. Routing correctly restricted search to `3M_2018_10K`, but the statement's
line item reads "Purchases of property, plant and equipment (PP&E)", and the top 5 were prose
chunks about capital leases and other cash flows (pages 83, 49, 26, 59 in 1-based numbering);
the statement itself (page 60) was not among them. The model declared insufficient evidence:
a safe failure.

### Table parse error leading to a wrong period
`financebench_id_07507`, oracle (the gold page was given). Adobe's FY2015 to FY2016 change in
operating income; reference 65.4%, system 118.83%. Our parsed income statement had the correct
values in the correct columns, but the header was degraded: the statement title was absorbed
into the first column's header ("CONSOLIDATED STATEMENTS OF INCOME (In thousands ...) December 2,
2016") and the spanning "Years Ended" caption attached only to the middle column. The model
labeled the middle column (fiscal 2015, 903,095) as 2016 and the right column (fiscal 2014) as
2015. Verification passed because both values really are on the cited page: it checks that
values exist, not which column they came from.

### Wrong period: answering a different year
Unanswerable probe `probe_period_12`, naive configuration: asked about Coca-Cola's FY2030
operating income, the naive pipeline answered with FY2022 figures "which can be considered as
FY2030". The best configuration abstained on all 30 probes.

### Arithmetic / metric definition
- `financebench_id_10130`, best. Corning FY2020 days payable outstanding; reference 63.86,
  system 310.27. The model built a denominator of cost of goods sold plus change in inventory
  and extracted an unused input. Python evaluated the formula exactly as given; the error is in
  the formula the model wrote.
- `financebench_id_02981`, best. Corning's three-year average operating margin; reference 10.3%
  (average of the three yearly margins), system 10.65% (three-year operating income over
  three-year net sales). Both are defensible definitions; the rubric's 1% tolerance marks it
  wrong.

### Unsupported claim
`financebench_id_00394`, best. "Which JPMorgan segment had the highest net income in Q2 2022?"
Reference: Corporate & Investment Bank. The system claimed Asset & Wealth Management and cited
pages 177 and 21 of the 10-Q. Page 21 is the gold page, and it shows Corporate & Investment Bank
with the highest net income: the model cited the right page and misread it. Citation
verification passed because the IDs were valid; this is the gap between "the citation points to
a retrieved page" and "the page supports the claim". (The rule placed it here because of a
flagged number, the "2" of "Q2"; the real failure is the misreading.)

### Likely judge errors (in "other")
`financebench_id_00382` ("Las Vegas Strip Resorts" vs reference "Las Vegas resorts contributed
about 90%") and `financebench_id_01275` (Best Buy's operating activities, $1,824 million, vs
reference "$1.8 bn") read as correct but were judged incorrect. The hand-labeled agreement study
quantifies how often this happens.

## What would fix the biggest buckets

1. **Within-document ranking (retrieval_miss):** add line-item synonyms to chunk text
   (capital expenditure ↔ purchases of property, plant and equipment), or route by statement
   type ("cash flow statement" → the statement's pages).
2. **Table headers (parse):** detect statement titles and spanning captions separately from
   column headers; repeat the year in each cell ("2016: 1,493,602") so the column is explicit.
3. **Support, not just existence (verification):** check that the cited page supports the claim
   (an entailment check), and record the column/period of every extracted value.
