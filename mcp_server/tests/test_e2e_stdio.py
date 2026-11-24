"""End to end: launch the server over stdio, connect with the SDK client, call every tool against the
real local stack (PostgreSQL + pgvector, the gateway, the model server, Ollama).

Skipped unless FINRAG_MCP_E2E=1 and GATEWAY_API_KEY are set (CI has no model stack).
"""

import os
import sys
from pathlib import Path

import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters

SERVER = Path(__file__).resolve().parents[1] / "server.py"
pytestmark = [
    pytest.mark.anyio,
    pytest.mark.skipif(os.environ.get("FINRAG_MCP_E2E") != "1" or not os.environ.get("GATEWAY_API_KEY"),
                       reason="needs the local stack: set FINRAG_MCP_E2E=1 and GATEWAY_API_KEY"),
]


def params() -> StdioServerParameters:
    return StdioServerParameters(command=sys.executable, args=[str(SERVER)], env=dict(os.environ))


async def test_every_tool_over_stdio_against_the_real_stack():
    async with Client(params(), read_timeout_seconds=360) as client:
        tools = {t.name for t in (await client.list_tools()).tools}
        assert tools == {"search_filings", "answer_question", "list_filings"}

        filings = (await client.call_tool("list_filings", {})).structured_content
        assert filings["count"] == 84 and "3M" in filings["companies"]

        search = await client.call_tool("search_filings", {"query": "3M capital expenditure", "company": "3M",
                                                           "fiscal_year": 2018, "k": 3})
        out = search.structured_content
        assert not search.is_error and out["status"] == "ok" and len(out["results"]) == 3
        assert all(r["doc_name"] == "3M_2018_10K" for r in out["results"])

        answer = await client.call_tool("answer_question",
                                        {"question": "What was AMD's total net revenue in FY2022?"})
        assert not answer.is_error
        rec = answer.structured_content
        assert rec["abstained"] or rec["citations"], "an answer must either cite pages or abstain"

        bad = await client.call_tool("search_filings", {"query": "revenue", "company": "Apple"})
        assert bad.is_error and "unknown_company" in bad.content[0].text
