# Answer correctness rubric

Used by both the LLM judge (`rag-service/src/finrag/eval/judge.py`) and the human labels
that validate it. Every answer gets one binary label.

**CORRECT** when the system's final answer matches the FinanceBench reference answer:

- **Numbers** match within 1% relative difference, or match after rounding to the
  reference's precision. Unit and scale must agree: millions vs thousands is a mismatch;
  0.103 and 10.3% are the same value.
- **Yes/no questions**: the yes/no must match, and no key supporting fact may contradict
  the reference.
- **Extra detail** that is correct does not hurt.

**INCORRECT** for anything else:

- a wrong, missing or differently scaled number;
- the wrong company or fiscal period;
- a key fact that contradicts the reference;
- an answer to a different question than the one asked.

**Abstentions** ("insufficient evidence") are not labeled; they are counted separately, as
coverage.

**Deterministic tolerance check.** The judge also reports the main number in the reference
and in the candidate. When both are present, Python applies the 1% rule and that decides the
label. Judge-human agreement is reported both with and without this check.
