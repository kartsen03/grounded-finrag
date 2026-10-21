"""Metadata routing: infer the company and fiscal period a question is about, and restrict
retrieval to that company's matching filings.

Fallback chain for the period, most specific first:
  1. filings for the latest fiscal year mentioned (and quarter, when one is mentioned);
  2. the following year's filings, which report that year as the comparative period;
  3. all of the company's filings.
No company recognized -> no filter (search the whole corpus).

Aliases come from the corpus metadata plus common names and tickers; they were not
derived from the test questions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from finrag.corpus import DocMeta

ALIASES: dict[str, list[str]] = {
    "3M": ["3M", "3M Company", "Minnesota Mining"],
    "AES Corporation": ["AES"],
    "AMD": ["AMD", "Advanced Micro Devices"],
    "Activision Blizzard": ["Activision Blizzard", "Activision"],
    "Adobe": ["Adobe"],
    "Amazon": ["Amazon", "Amazon.com"],
    "Amcor": ["Amcor"],
    "American Express": ["American Express", "AmEx", "AXP"],
    "American Water Works": ["American Water Works", "American Water"],
    "Best Buy": ["Best Buy", "BestBuy"],
    "Block": ["Block", "Square"],
    "Boeing": ["Boeing"],
    "CVS Health": ["CVS Health", "CVS"],
    "Coca-Cola": ["Coca-Cola", "Coca Cola", "CocaCola", "Coke"],
    "Corning": ["Corning"],
    "Costco": ["Costco"],
    "Foot Locker": ["Foot Locker", "FootLocker"],
    "General Mills": ["General Mills"],
    "JPMorgan": ["JPMorgan", "JP Morgan", "J.P. Morgan", "JPMorgan Chase", "JPM"],
    "Johnson & Johnson": ["Johnson & Johnson", "Johnson and Johnson", "J&J", "JNJ"],
    "Kraft Heinz": ["Kraft Heinz", "Kraft", "Heinz"],
    "Lockheed Martin": ["Lockheed Martin", "Lockheed"],
    "MGM Resorts": ["MGM Resorts", "MGM"],
    "Microsoft": ["Microsoft", "MSFT"],
    "Netflix": ["Netflix"],
    "Nike": ["Nike"],
    "Paypal": ["PayPal"],
    "PepsiCo": ["PepsiCo", "Pepsi"],
    "Pfizer": ["Pfizer"],
    "Ulta Beauty": ["Ulta Beauty", "Ulta"],
    "Verizon": ["Verizon"],
    "Walmart": ["Walmart", "Wal-Mart"],
}
# Aliases that are also ordinary English words only match with their capitalization.
CASE_SENSITIVE = {"Block", "Square", "Coke"}

_YEAR = re.compile(r"\b(?:FY\s?|fiscal(?:\s+year)?\s+)?((?:19|20)\d{2})\b", re.IGNORECASE)
_SHORT_FY = re.compile(r"\bFY'?(\d{2})\b", re.IGNORECASE)
_QUARTER = re.compile(r"\bQ([1-4])\b|\b([1-4])Q\b|\b(first|second|third|fourth)[\s-]+quarter\b", re.IGNORECASE)
_ORDINAL = {"first": 1, "second": 2, "third": 3, "fourth": 4}


def _alias_patterns() -> list[tuple[re.Pattern, str]]:
    patterns = []
    for company, names in ALIASES.items():
        for name in names:
            flags = 0 if name in CASE_SENSITIVE else re.IGNORECASE
            patterns.append((re.compile(rf"(?<![\w&]){re.escape(name)}(?![\w&])", flags), company))
    return patterns


_PATTERNS = _alias_patterns()


def detect_companies(question: str) -> set[str]:
    return {company for pattern, company in _PATTERNS if pattern.search(question)}


def detect_years(question: str) -> list[int]:
    years = [int(m.group(1)) for m in _YEAR.finditer(question)]
    years += [2000 + int(m.group(1)) for m in _SHORT_FY.finditer(question)]
    return years


def detect_quarter(question: str) -> int | None:
    m = _QUARTER.search(question)
    if not m:
        return None
    if m.group(1) or m.group(2):
        return int(m.group(1) or m.group(2))
    return _ORDINAL[m.group(3).lower()]


@dataclass(frozen=True)
class Route:
    companies: frozenset[str]
    doc_names: frozenset[str] | None  # None = no filter
    rule: str  # which step of the fallback chain applied


def route(question: str, docs: list[DocMeta]) -> Route:
    companies = frozenset(detect_companies(question))
    if not companies:
        return Route(companies, None, "no_company")
    candidates = [d for d in docs if d.company in companies]
    if not candidates:
        return Route(companies, None, "company_not_in_corpus")
    years = detect_years(question)
    quarter = detect_quarter(question)
    if years:
        year = max(years)
        same_year = [d for d in candidates if d.fiscal_year == year]
        if quarter is not None:
            same_quarter = [d for d in same_year if d.fiscal_quarter == quarter]
            if same_quarter:
                return Route(companies, frozenset(d.doc_name for d in same_quarter), "year_quarter")
        if same_year:
            return Route(companies, frozenset(d.doc_name for d in same_year), "year")
        next_year = [d for d in candidates if d.fiscal_year == year + 1]
        if next_year:
            return Route(companies, frozenset(d.doc_name for d in next_year), "next_year")
    return Route(companies, frozenset(d.doc_name for d in candidates), "company")
