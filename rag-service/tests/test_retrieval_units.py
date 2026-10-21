import numpy as np

from finrag.corpus import DocMeta
from finrag.retrieval import routing
from finrag.retrieval.bm25 import BM25, tokenize
from finrag.retrieval.fusion import rrf


def test_tokenize_drops_thousands_separators_and_stopwords():
    assert tokenize("Purchases of PP&E were $1,577 in FY2018") == ["purchases", "pp", "e", "1577", "fy2018"]


def test_bm25_prefers_rare_matching_terms_and_handles_unknown_queries():
    docs = ["capital expenditure purchases of property plant equipment 1,577",
            "revenue grew in the quarter", "revenue and revenue again"]
    bm25 = BM25(docs)
    scores = bm25.scores("capital expenditure 1577")
    assert int(np.argmax(scores)) == 0
    assert not bm25.scores("zzz").any()


def test_rrf_rewards_agreement_and_is_deterministic():
    fused = rrf([["a", "b", "c"], ["b", "a", "d"]], k=60)
    assert [d for d, _ in fused][:2] in (["a", "b"], ["b", "a"])
    assert fused[0][1] == fused[1][1]  # symmetric ranks -> tie, broken by id
    assert [d for d, _ in fused] == ["a", "b", "c", "d"]


DOCS = [
    DocMeta("ACME_2021_10K", "Boeing", "10-K", 2021, None, None, "x"),
    DocMeta("ACME_2022_10K", "Boeing", "10-K", 2022, None, None, "x"),
    DocMeta("ACME_2023Q2_10Q", "Boeing", "10-Q", 2023, 2, None, "x"),
    DocMeta("SQ_2016_10K", "Block", "10-K", 2016, None, None, "x"),
]


def test_route_year_quarter_and_fallbacks():
    assert routing.route("What was Boeing's FY2022 revenue?", DOCS).doc_names == {"ACME_2022_10K"}
    r = routing.route("Boeing gross margin in Q2 of FY2023", DOCS)
    assert (r.doc_names, r.rule) == ({"ACME_2023Q2_10Q"}, "year_quarter")
    r = routing.route("Boeing revenue in FY2020?", DOCS)  # no 2020 filing -> 2021 10-K reports 2020
    assert (r.doc_names, r.rule) == ({"ACME_2021_10K"}, "next_year")
    assert routing.route("How has Boeing's backlog changed?", DOCS).rule == "company"
    assert routing.route("What is the capital of France?", DOCS).doc_names is None


def test_route_uses_latest_year_and_case_sensitive_aliases():
    r = routing.route("Change in Boeing revenue from FY2021 to FY2022", DOCS)
    assert r.doc_names == {"ACME_2022_10K"}
    assert routing.route("What was Square's FY2016 working capital?", DOCS).companies == {"Block"}
    assert routing.route("a block of shares was sold in 2016", DOCS).companies == frozenset()
