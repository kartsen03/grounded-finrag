import json

import pytest

from finrag.answer import classify
from finrag.answer.numbers import FormulaError, evaluate, grounded, parse_number
from finrag.answer.pipeline import verify_extract, verify_grounded

SOURCES = {
    "S1": {"id": "S1", "doc_name": "3M_2018_10K", "page": 60,
           "text": "| Purchases of property, plant and equipment (PP&E) | (1,577) | (1,373) |"},
    "S2": {"id": "S2", "doc_name": "3M_2018_10K", "page": 58,
           "text": "| Total current assets | 13,709 |\n| Total current liabilities | 7,244 |"},
}


def test_parse_number_formats():
    assert parse_number("(1,577)") == -1577
    assert parse_number("$5,363") == 5363
    assert parse_number("12.5%") == 12.5
    assert parse_number("abc") is None


def test_grounding_is_sign_insensitive_but_exact():
    assert grounded(1577, SOURCES["S1"]["text"])
    assert grounded(-1577, SOURCES["S1"]["text"])
    assert not grounded(1578, SOURCES["S1"]["text"])


def test_evaluate_allows_arithmetic_only():
    assert evaluate("(a - b) / b * 100", {"a": 110, "b": 100}) == pytest.approx(10.0)
    for bad in ["__import__('os')", "a.real", "a ** 2", "c + 1", "a / 0"]:
        with pytest.raises(FormulaError):
            evaluate(bad, {"a": 1.0, "b": 2.0})


def test_verify_grounded_rejects_unknown_source_ids_and_flags_ungrounded_numbers():
    reply = json.dumps({"insufficient_evidence": False, "answer": "Capex was $1,577 million.",
                        "claims": [{"statement": "3M capex was $1,577 million in FY2018.", "source_ids": ["S1"]},
                                   {"statement": "It rose 15%.", "source_ids": ["S9"]}]})
    result = verify_grounded(reply, SOURCES)
    assert any("S9" in e for e in result["errors"])
    ok = verify_grounded(json.dumps({"insufficient_evidence": False, "answer": "x",
                                     "claims": [{"statement": "Capex was 1,577 or 1,600.", "source_ids": ["S1"]}]}),
                         SOURCES)
    assert ok["errors"] == []
    assert ok["citations"] == [["3M_2018_10K", 60]]
    assert ok["ungrounded_numbers"] == [{"claim": 1, "value": 1600.0}]


def test_verify_extract_computes_from_grounded_inputs():
    reply = json.dumps({"insufficient_evidence": False, "metric": "current ratio", "unit": "ratio",
                        "formula": "current_assets / current_liabilities",
                        "inputs": [{"name": "current_assets", "line_item": "Total current assets", "period": "FY2018",
                                    "value": 13709, "source_id": "S2"},
                                   {"name": "current_liabilities", "line_item": "Total current liabilities",
                                    "period": "FY2018", "value": 7244, "source_id": "S2"}]})
    result = verify_extract(reply, SOURCES)
    assert result["errors"] == []
    assert result["computation"]["result"] == pytest.approx(13709 / 7244)
    assert "[3M_2018_10K, p.58]" in result["answer"]


def test_verify_extract_rejects_values_not_on_the_cited_page():
    reply = json.dumps({"insufficient_evidence": False, "metric": "capex", "unit": "USD millions",
                        "formula": "capex", "inputs": [{"name": "capex", "line_item": "PP&E", "period": "FY2018",
                                                        "value": 1600, "source_id": "S1"}]})
    assert any("does not appear" in e for e in verify_extract(reply, SOURCES)["errors"])


def test_insufficient_evidence_and_bad_json():
    assert verify_grounded(json.dumps({"insufficient_evidence": True, "answer": "", "claims": []}),
                           SOURCES)["insufficient"]
    assert verify_extract("not json", SOURCES)["errors"] == ["the reply is not valid JSON"]


def test_numeric_classifier():
    assert classify.is_numeric("What is the FY2018 capital expenditure amount (in USD millions) for 3M?")
    assert classify.is_numeric("What is Block's FY2016 working capital ratio?")
    assert not classify.is_numeric("Does AMD have a significant customer concentration?")
