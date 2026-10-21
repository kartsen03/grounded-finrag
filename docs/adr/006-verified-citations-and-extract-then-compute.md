# ADR 006: Verified citations via source IDs, and extract-then-compute for numbers

**Status:** accepted (2026-10-21)

**Decision.**
- Sources are shown to the model as `[S1]`..`[S5]`. The model returns JSON (Ollama structured
  output with a JSON Schema): claims, each with the source IDs that state it. A citation that
  names an ID that was never provided fails verification, as does a claim with no citation.
  The service maps IDs back to `[document, page]`, so displayed citations are always exact.
- Numbers in claims that do not appear on the cited pages are flagged (`ungrounded_numbers`).
- Numeric questions (keyword classifier) use extract-then-compute: the model returns line items
  (value as printed, period, source ID) and a formula over their names. Python checks each value
  against the text of its cited source, then evaluates the formula with an AST walker that
  allows only `+ - * /`, parentheses, numbers and the extracted names (no calls, attributes or
  other names, so model output cannot run code).
- A failed check gets one repair round with the errors listed; a second failure abstains.

**Consequences.** Arithmetic errors move out of the model and into checked code; extraction
errors (wrong line item, wrong period, wrong metric definition) remain and are measured in the
error analysis. Normalizing `"[S2]"` to `S2` was needed because the model often adds brackets.
