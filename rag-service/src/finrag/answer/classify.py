"""Decide whether a question asks for a computed or directly read financial number.

Numeric questions go through extract-then-compute. The rule is a keyword pattern, chosen to
be readable rather than clever; its agreement with FinanceBench's question types on the dev
split is reported by the evaluation.
"""

from __future__ import annotations

import re

NUMERIC = re.compile(
    r"\b(ratio|margin|percent(age)?|growth|change|increase|decrease|average|turnover|days|dpo|dso|dio|"
    r"roa|roe|return on|per share|eps|free cash flow|working capital|coverage|year[- ]over[- ]year|"
    r"yoy|cagr|compounded|round(ed)? to|calculate|compute|how much|what (is|was) the (fy|fiscal)?\s*\d{0,4}\s*"
    r"(total|net|gross|operating|capital|cash))\b|%|\bin usd (millions|billions|thousands)\b",
    re.IGNORECASE)


def is_numeric(question: str) -> bool:
    return bool(NUMERIC.search(question))
