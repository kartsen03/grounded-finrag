"""Tool handlers through a real MCP client session (in-process), with the backend faked."""

import json
import time

import anyio
import httpx
import psycopg
import pytest
from mcp import Client

from mcp_server import server as srv

FILINGS = [
    {"doc_name": "3M_2018_10K", "company": "3M", "doc_type": "10-K", "fiscal_year": 2018, "fiscal_quarter": None,
     "chunks": 400},
    {"doc_name": "AMD_2022_10K", "company": "AMD", "doc_type": "10-K", "fiscal_year": 2022, "fiscal_quarter": None,
     "chunks": 300},
]
HIT = {"doc_name": "3M_2018_10K", "page": 60, "section": "Item 8", "score": 0.0325,
       "text": "| Purchases of property, plant and equipment (PP&E) | (1,577) |"}


class FakeBackend:
    def __init__(self, hits=None, answer=None, error=None, delay=0.0):
        self.hits = [HIT] if hits is None else hits
        self.answer_rec = answer
        self.error = error
        self.delay = delay
        self.calls = []
        self.list_calls = 0

    def _maybe_fail(self):
        if self.delay:
            time.sleep(self.delay)
        if self.error:
            raise self.error

    def list_filings(self):
        self.list_calls += 1
        if self.delay:
            time.sleep(self.delay)
        return FILINGS

    def search(self, query, doc_names, k, request_id):
        self.calls.append(("search", query, doc_names, k, request_id))
        self._maybe_fail()
        return self.hits[:k]

    def answer(self, question, company, request_id):
        self.calls.append(("answer", question, company, request_id))
        self._maybe_fail()
        return self.answer_rec


def http_error(status, headers=None):
    req = httpx.Request("POST", "http://gw/v1/chat/completions")
    return httpx.HTTPStatusError("x", request=req, response=httpx.Response(status, headers=headers, request=req))


def error_of(result):
    assert result.is_error
    text = result.content[0].text  # the SDK prefixes "Error executing tool <name>: "
    return json.loads(text[text.index("{"):])["error"]


async def call(backend, tool, args=None):
    async with Client(srv.build_server(backend)) as client:
        return await client.call_tool(tool, args or {})


pytestmark = pytest.mark.anyio


async def test_tools_are_listed_read_only_with_typed_schemas():
    async with Client(srv.build_server(FakeBackend())) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
    assert set(tools) == {"search_filings", "answer_question", "list_filings"}
    assert all(t.annotations.read_only_hint and not t.annotations.destructive_hint for t in tools.values())
    k = tools["search_filings"].input_schema["properties"]["k"]
    assert (k["minimum"], k["maximum"], k["default"]) == (1, 10, 5)
    assert tools["search_filings"].input_schema["required"] == ["query"]
    assert tools["answer_question"].output_schema is not None


async def test_search_success_returns_citations():
    backend = FakeBackend()
    res = await call(backend, "search_filings", {"query": "3M capex FY2018", "company": "3m", "fiscal_year": 2018})
    out = res.structured_content
    assert not res.is_error and out["status"] == "ok"
    assert out["results"][0]["citation"] == "[3M_2018_10K, p.60]"
    assert out["filter"]["company"] == "3M" and out["filter"]["documents"] == ["3M_2018_10K"]
    assert backend.calls[0][2] == frozenset({"3M_2018_10K"})
    assert out["request_id"].startswith("mcp-") and "untrusted" in out["notice"]


async def test_search_without_hits_is_no_evidence_not_error():
    res = await call(FakeBackend(hits=[]), "search_filings", {"query": "something obscure"})
    assert not res.is_error and res.structured_content["status"] == "no_evidence"


async def test_answer_success_and_abstention():
    rec = {"answer": "Capex was $1,577 million. [3M_2018_10K, p.60]", "abstained": False, "mode": "extract",
           "citations": [["3M_2018_10K", 60]], "computation": {"result": 1577.0}, "support": 0.99}
    out = (await call(FakeBackend(answer=rec), "answer_question", {"question": "3M FY2018 capex?"})).structured_content
    assert out["citations"][0]["citation"] == "[3M_2018_10K, p.60]" and out["abstained"] is False

    abst = {"answer": "Insufficient evidence in the retrieved filings to answer this question.", "abstained": True,
            "abstain_reason": "weak_retrieval_support", "mode": "grounded", "citations": [], "support": 0.2}
    res = await call(FakeBackend(answer=abst), "answer_question", {"question": "Apple FY2022 revenue?"})
    assert not res.is_error  # abstaining is a valid answer, not a tool error
    assert res.structured_content["abstained"] is True
    assert res.structured_content["abstain_reason"] == "weak_retrieval_support"


async def test_answer_passes_canonical_company():
    backend = FakeBackend(answer={"answer": "x", "abstained": True, "mode": "grounded", "citations": []})
    await call(backend, "answer_question", {"question": "capex in 2018?", "company": "3m"})
    assert backend.calls[0][2] == "3M"


@pytest.mark.parametrize("args", [
    {"query": "3M capex", "k": 50},
    {"query": "ab"},
    {"query": "3M capex", "fiscal_year": 1800},
    {"query": "x" * 1001},
    {},
])
async def test_invalid_inputs_are_rejected_before_the_backend(args):
    backend = FakeBackend()
    res = await call(backend, "search_filings", args)
    assert res.is_error and backend.calls == []


async def test_unknown_company_and_missing_year_are_structured_errors():
    err = error_of(await call(FakeBackend(), "search_filings", {"query": "revenue", "company": "Apple"}))
    assert err["code"] == "unknown_company" and "list_filings" in err["message"]
    err = error_of(await call(FakeBackend(), "search_filings", {"query": "revenue", "company": "3M",
                                                                 "fiscal_year": 2030}))
    assert err["code"] == "no_matching_filings" and "2018" in err["message"]


async def test_timeout_becomes_retryable_error(monkeypatch):
    monkeypatch.setattr(srv, "SEARCH_DEADLINE_S", 0.2)
    err = error_of(await call(FakeBackend(delay=1.0), "search_filings", {"query": "3M capex"}))
    assert err == {"code": "timeout", "message": "The backend did not respond in time.", "retryable": True}


@pytest.mark.parametrize("exc,code,retryable", [
    (http_error(429, {"Retry-After": "17"}), "rate_limited", True),
    (http_error(401), "gateway_unauthorized", False),
    (http_error(502), "gateway_error", True),
    (httpx.ConnectError("refused"), "backend_unavailable", True),
    (httpx.ReadTimeout("slow"), "timeout", True),
    (psycopg.OperationalError("db down"), "database_unavailable", True),
])
async def test_gateway_and_backend_failures_map_to_codes(exc, code, retryable):
    err = error_of(await call(FakeBackend(error=exc), "answer_question", {"question": "3M FY2018 capex?"}))
    assert (err["code"], err["retryable"]) == (code, retryable)
    if code == "rate_limited":
        assert "17" in err["message"]


async def test_unexpected_errors_do_not_leak_details():
    err = error_of(await call(FakeBackend(error=RuntimeError("secret=sk-abc /internal/path")), "search_filings",
                              {"query": "3M capex"}))
    assert err["code"] == "internal_error"
    assert "sk-abc" not in err["message"] and "internal/path" not in err["message"]


async def test_list_filings_and_text_sanitizing():
    out = (await call(FakeBackend(), "list_filings")).structured_content
    assert out["count"] == 2 and out["companies"] == ["3M", "AMD"]
    dirty = dict(HIT, text="ok\x00\x07" + "y" * 3000)
    res = await call(FakeBackend(hits=[dirty]), "search_filings", {"query": "3M capex"})
    text = res.structured_content["results"][0]["text"]
    assert "\x00" not in text and text.endswith("[truncated]") and len(text) <= srv.MAX_CHUNK_CHARS + 20


async def test_parallel_first_calls_fill_the_filings_cache_once():
    # Regression: Claude Code issued search_filings and answer_question in parallel, both filled the
    # empty cache, and list_filings then reported every filing twice.
    backend = FakeBackend(answer={"answer": "x", "abstained": True, "abstain_reason": "weak", "mode": "grounded",
                                  "citations": []}, delay=0.3)
    async with Client(srv.build_server(backend)) as client:
        async with anyio.create_task_group() as tg:
            tg.start_soon(client.call_tool, "search_filings", {"query": "3M capex", "company": "3M"})
            tg.start_soon(client.call_tool, "answer_question", {"question": "3M capex?", "company": "3M"})
        out = (await client.call_tool("list_filings", {})).structured_content
    assert out["count"] == len(FILINGS) and backend.list_calls == 1


def test_backend_requires_api_key_from_environment(monkeypatch):
    from mcp_server.backend import FinragBackend

    monkeypatch.delenv("GATEWAY_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GATEWAY_API_KEY"):
        FinragBackend.from_env()
