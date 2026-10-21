"""LLM judge for answer correctness, called through the gateway like every other model call.

Rubric (also in docs/judge_rubric.md):
  CORRECT    the candidate's final answer matches the reference answer. Numbers match within
             1% relative difference, or after rounding to the reference's precision, in the same
             unit and scale (millions vs thousands matter; 0.103 and 10.3% are the same value).
             For yes/no questions the yes/no must match and no key fact may contradict the
             reference. Extra correct detail is fine.
  INCORRECT  anything else: a wrong or missing number, the wrong period or company, a
             contradicted key fact, or an answer to a different question.
Abstentions are not sent to the judge; they are scored as abstentions.

The judge also extracts the main number from the reference and the candidate. When both are
present, a deterministic 1% tolerance check decides the verdict ("judge+tolerance"), because
LLMs compare numbers unreliably. Agreement with human labels is reported for both variants.
"""

from __future__ import annotations

import json
import math

from finrag.gateway_client import GatewayClient

JUDGE_ALIAS = "local-chat"
REL_TOL = 0.01

SYSTEM = """You grade answers to questions about company financial filings against a reference answer.
Verdict CORRECT if the candidate's final answer matches the reference:
- numbers must match within 1% relative difference, or after rounding to the reference's precision,
  in the same unit and scale (millions vs thousands matter; 0.103 and 10.3% are the same value);
- for yes/no questions the yes/no must match and no key fact may contradict the reference;
- extra correct detail is fine.
Verdict INCORRECT for a wrong or missing number, the wrong company or period, a contradicted key fact,
or an answer to a different question.
Also report the single main numeric value stated in the reference and in the candidate (as plain
numbers, percentages without the % sign), or null if there is none.
Reply with JSON only."""

SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["CORRECT", "INCORRECT"]},
        "reason": {"type": "string"},
        "reference_value": {"type": ["number", "null"]},
        "candidate_value": {"type": ["number", "null"]},
    },
    "required": ["verdict", "reason", "reference_value", "candidate_value"],
}


def within_tolerance(reference: float, candidate: float, rel_tol: float = REL_TOL) -> bool:
    if reference == 0:
        return math.isclose(candidate, 0.0, abs_tol=1e-9)
    return abs(candidate - reference) / abs(reference) <= rel_tol


def judge(gateway: GatewayClient, question: str, reference: str, candidate: str, request_id: str) -> dict:
    user = f"Question: {question}\n\nReference answer: {reference}\n\nCandidate answer: {candidate}"
    reply = gateway.chat([{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
                         JUDGE_ALIAS, request_id=request_id, temperature=0.0, seed=0, max_tokens=300,
                         json_schema=SCHEMA)
    try:
        data = json.loads(reply.content)
    except json.JSONDecodeError:
        data = {"verdict": "INCORRECT", "reason": "judge reply was not valid JSON", "reference_value": None,
                "candidate_value": None}
    raw_correct = data.get("verdict") == "CORRECT"
    ref, cand = data.get("reference_value"), data.get("candidate_value")
    numeric = isinstance(ref, (int, float)) and isinstance(cand, (int, float))
    final = within_tolerance(float(ref), float(cand)) if numeric else raw_correct
    return {"judge_correct": raw_correct, "correct": final, "tolerance_applied": numeric,
            "reference_value": ref, "candidate_value": cand, "reason": data.get("reason", ""),
            "judge_tokens": reply.prompt_tokens + reply.completion_tokens}


def cohen_kappa(a: list[bool], b: list[bool]) -> float:
    """Agreement beyond chance for two binary raters: (p_o - p_e) / (1 - p_e)."""
    n = len(a)
    p_o = sum(x == y for x, y in zip(a, b)) / n
    pa, pb = sum(a) / n, sum(b) / n
    p_e = pa * pb + (1 - pa) * (1 - pb)
    return 1.0 if p_e == 1 else (p_o - p_e) / (1 - p_e)
