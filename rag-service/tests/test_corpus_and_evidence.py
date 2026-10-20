from finrag.corpus import doc_meta_from_row, evidence_pages
from finrag.ingest.evidence_check import check


def _row(name, doc_type, period=2022):
    return {"doc_name": name, "company": "Acme", "doc_type": doc_type, "doc_period": period,
            "gics_sector": "Industrials"}


def test_doc_meta_periods():
    assert doc_meta_from_row(_row("ACME_2018_10K", "10k", 2018)).period_label == "FY2018"
    q = doc_meta_from_row(_row("ACME_2023Q2_10Q", "10q", 2023))
    assert (q.fiscal_year, q.fiscal_quarter, q.doc_type) == (2023, 2, "10-Q")
    k8 = doc_meta_from_row(_row("ACME_2022_8K_dated-2022-07-01", "8k"))
    assert k8.filing_date == "2022-07-01" and k8.doc_type == "8-K"
    assert doc_meta_from_row(_row("ACME_2022_8K_dated_2022-08-19", "8k")).filing_date == "2022-08-19"
    assert doc_meta_from_row(_row("ACME_2023Q4_EARNINGS", "Earnings", 2023)).header == "Acme Earnings release FY2023 Q4"


def test_evidence_pages_are_zero_based_ints():
    q = {"evidence": [{"doc_name": "D", "evidence_page_num": "59"}, {"doc_name": "D", "evidence_page_num": 3}]}
    assert evidence_pages(q) == {("D", 59), ("D", 3)}


def test_evidence_check_detects_off_by_one():
    q = {"q1": {"evidence": [{"doc_name": "D", "evidence_page_num": "5",
                              "evidence_text": "purchases of property plant equipment 1577"}]}}
    pages = {("D", 4): "purchases of property plant and equipment 1,577", ("D", 5): "unrelated text here"}
    result = check(q, pages)
    assert result["outcomes"]["best_is_p_minus_1"] == 1
