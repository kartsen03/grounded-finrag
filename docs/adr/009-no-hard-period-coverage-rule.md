# ADR 009: No hard "period not covered" abstention rule

**Status:** accepted (2026-10-21)

**Context.** A question about a fiscal year with no filing in the corpus (for example FY2030)
cannot be answered. A tempting rule: abstain before generation when no filing for that company
covers the year (a 10-K for year y+2 still reports year y).

**Evidence (dev only).** The rule would wrongly abstain on 2 of 75 dev questions, for example a
question about FY2024 whose answer is in a filing labeled 2023: companies name fiscal years
differently from the calendar labels in the metadata.

**Decision.** No hard rule. Period mismatches are left to the model (instructed to declare
insufficient evidence) and to the support-score threshold, and measured with the unanswerable
probe set (15 future-period questions).
