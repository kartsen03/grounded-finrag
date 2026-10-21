"""Prompts and JSON schemas for answer generation.

Sources are shown to the model as [S1] ... [Sk]; the model cites source IDs, and the service
maps them back to [document, page]. Asking for IDs instead of free-text citations makes a
fabricated citation detectable (an ID that was never provided) and keeps citations exact.
"""

from __future__ import annotations

GROUNDED_SYSTEM = """You answer questions about company financial filings using ONLY the sources provided.
Each source starts with an ID such as [S1], followed by its document and page.
Rules:
1. Break the answer into short factual claims. Every claim must list the IDs of the sources that state it.
2. Use only facts and numbers that appear in the cited sources. Do not use outside knowledge.
3. If the sources do not contain what is needed for the company and fiscal period asked about,
   set insufficient_evidence to true and leave claims empty.
4. "answer" is a direct answer to the question in at most 60 words. Use at most 5 claims.
Reply with JSON only."""

GROUNDED_SCHEMA = {
    "type": "object",
    "properties": {
        "insufficient_evidence": {"type": "boolean"},
        "answer": {"type": "string"},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"statement": {"type": "string"},
                               "source_ids": {"type": "array", "items": {"type": "string"}}},
                "required": ["statement", "source_ids"],
            },
        },
    },
    "required": ["insufficient_evidence", "answer", "claims"],
}

EXTRACT_SYSTEM = """You prepare a financial calculation from company filings. Do NOT do any arithmetic yourself.
Using ONLY the sources provided (each starts with an ID such as [S1]):
1. Decide which line items the question needs. For each, give a short snake_case name, the line item
   label as printed, the fiscal period, the value exactly as printed (as a plain number; parentheses
   mean negative), and the ID of the source it comes from.
2. Write "formula" as arithmetic over those names using only + - * / and parentheses, e.g.
   "(revenue_2022 - revenue_2021) / revenue_2021 * 100". Include unit conversions as numbers in the
   formula (e.g. "/ 1000" to go from thousands to millions). A value read directly needs a formula
   that is just its name.
3. "unit" is the unit of the final result (e.g. "USD millions", "%", "ratio", "days").
4. If the sources lack any needed line item for the company and period asked about, set
   insufficient_evidence to true and leave inputs empty.
Reply with JSON only."""

EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "insufficient_evidence": {"type": "boolean"},
        "metric": {"type": "string"},
        "inputs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "line_item": {"type": "string"},
                               "period": {"type": "string"}, "value": {"type": "number"},
                               "source_id": {"type": "string"}},
                "required": ["name", "line_item", "period", "value", "source_id"],
            },
        },
        "formula": {"type": "string"},
        "unit": {"type": "string"},
    },
    "required": ["insufficient_evidence", "metric", "inputs", "formula", "unit"],
}

# Naive baseline: plain RAG prompt, free-text answer, no structure, no verification.
NAIVE_SYSTEM = """Answer the question about company financial filings using the sources provided.
Cite sources inline as [document, page]. Be concise."""


def render_sources(sources: list[dict]) -> str:
    blocks = []
    for s in sources:
        header = f"[{s['id']}] {s['doc_name']} page {s['page']}"
        if s.get("section"):
            header += f" ({s['section'][:80]})"
        blocks.append(f"{header}\n{s['text']}")
    return "\n\n".join(blocks)


def user_message(question: str, sources: list[dict]) -> str:
    return f"Sources:\n\n{render_sources(sources)}\n\nQuestion: {question}"


def repair_message(errors: list[str]) -> str:
    listed = "\n".join(f"- {e}" for e in errors)
    return (f"Your previous reply failed verification:\n{listed}\n"
            "Fix these problems using only the sources above, and reply with corrected JSON only.")
