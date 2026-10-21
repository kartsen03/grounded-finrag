import json

from finrag.answer.pipeline import INSUFFICIENT, AnswerConfig, Answerer
from finrag.gateway_client import ChatReply
from finrag.retrieval.pipeline import Hit, RetrievalConfig, RetrievalResult

CHUNK = {"chunk_id": "D::structure::00001", "doc_name": "ACME_2022_10K", "page_idx": 9, "section": "Item 8",
         "text": "| Net sales | 4,210 | 3,880 |\n| Cost of sales | 2,945 | 2,790 |", "embed_text": "Acme 10-K | Net sales"}


class FakeRetriever:
    def retrieve(self, question, cfg, request_id=None):
        return RetrievalResult([Hit(CHUNK, 1.0)], None, {"total": 1.0})


class FakeGateway:
    """Returns scripted chat replies in order and a fixed support score."""

    def __init__(self, replies, support=0.8):
        self.replies = list(replies)
        self.support = support
        self.messages = []

    def rerank(self, query, documents, model, request_id=None):
        return [self.support] * len(documents)

    def chat(self, messages, model, request_id=None, **kwargs):
        self.messages.append(messages)
        return ChatReply(self.replies.pop(0), 100, 20, 5, "fake", request_id or "r")


def grounded(claim_ids, answer="Net sales were 4,210 million."):
    return json.dumps({"claims": [{"statement": answer, "source_ids": claim_ids}], "answer": answer,
                       "insufficient_evidence": False})


CFG = AnswerConfig("t", RetrievalConfig("structure", "hybrid", True, False, top_k=5), mode="grounded")


def test_valid_answer_passes_first_time_with_mapped_citation():
    gw = FakeGateway([grounded(["S1"])])
    rec = Answerer(gw, FakeRetriever()).answer("Acme net sales FY2022?", CFG)
    assert not rec["abstained"]
    assert rec["citations"] == [["ACME_2022_10K", 10]]  # 1-based page
    assert rec["verification"]["attempts"] == 1


def test_invalid_citation_is_repaired_once():
    gw = FakeGateway([grounded(["S4"]), grounded(["[S1]"])])
    rec = Answerer(gw, FakeRetriever()).answer("Acme net sales FY2022?", CFG)
    assert not rec["abstained"] and rec["verification"]["repaired"]
    assert "S4" in gw.messages[1][-1]["content"]  # the repair prompt names the bad citation


def test_still_invalid_after_repair_abstains():
    gw = FakeGateway([grounded(["S4"]), grounded(["S9"])])
    rec = Answerer(gw, FakeRetriever()).answer("Acme net sales FY2022?", CFG)
    assert rec["abstained"] and rec["abstain_reason"] == "verification_failed"
    assert rec["answer"] == INSUFFICIENT


def test_low_support_triggers_abstention_after_generation():
    gw = FakeGateway([grounded(["S1"])], support=0.05)
    cfg = AnswerConfig("t", CFG.retrieval, mode="grounded", abstain_threshold=0.1)
    rec = Answerer(gw, FakeRetriever()).answer("Acme net sales FY2022?", cfg)
    assert rec["abstained"] and rec["abstain_reason"] == "weak_retrieval_support"
    assert "4,210" in rec["answer_before_abstention"]


def test_extract_mode_computes_gross_margin():
    reply = json.dumps({"insufficient_evidence": False, "metric": "gross margin", "unit": "%",
                        "formula": "(net_sales - cost_of_sales) / net_sales * 100",
                        "inputs": [{"name": "net_sales", "line_item": "Net sales", "period": "2022", "value": 4210,
                                    "source_id": "S1"},
                                   {"name": "cost_of_sales", "line_item": "Cost of sales", "period": "2022",
                                    "value": 2945, "source_id": "S1"}]})
    gw = FakeGateway([reply])
    cfg = AnswerConfig("t", CFG.retrieval, mode="auto")
    rec = Answerer(gw, FakeRetriever()).answer("What is Acme's FY2022 gross margin?", cfg)
    assert rec["mode"] == "extract" and not rec["abstained"]
    assert abs(rec["computation"]["result"] - (4210 - 2945) / 4210 * 100) < 1e-9
