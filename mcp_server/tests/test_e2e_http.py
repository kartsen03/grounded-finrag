"""End to end over streamable HTTP: start the server on a loopback port, connect with the SDK client,
call the tools against the real local stack.

Skipped unless FINRAG_MCP_E2E=1 and GATEWAY_API_KEY are set (CI has no model stack). This covers the
SDK client only; no third-party HTTP client has been tested against this transport.
"""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from mcp import Client

SERVER = Path(__file__).resolve().parents[1] / "server.py"
pytestmark = [
    pytest.mark.anyio,
    pytest.mark.skipif(os.environ.get("FINRAG_MCP_E2E") != "1" or not os.environ.get("GATEWAY_API_KEY"),
                       reason="needs the local stack: set FINRAG_MCP_E2E=1 and GATEWAY_API_KEY"),
]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def http_server():
    port = free_port()
    proc = subprocess.Popen([sys.executable, str(SERVER), "--transport", "streamable-http", "--port", str(port)],
                            env=dict(os.environ), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                socket.create_connection(("127.0.0.1", port), timeout=1).close()
                break
            except OSError:
                time.sleep(0.5)
        else:
            pytest.fail("server did not start listening within 60 s")
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        proc.terminate()
        proc.wait(timeout=30)


async def test_tools_over_streamable_http(http_server):
    async with Client(http_server, read_timeout_seconds=360) as client:
        tools = {t.name for t in (await client.list_tools()).tools}
        assert tools == {"search_filings", "answer_question", "list_filings"}

        filings = await client.call_tool("list_filings", {})
        assert not filings.is_error and filings.structured_content["count"] == 84

        search = await client.call_tool("search_filings", {"query": "3M capital expenditure", "company": "3M",
                                                           "fiscal_year": 2018, "k": 2})
        out = search.structured_content
        assert not search.is_error and out["status"] == "ok" and len(out["results"]) == 2

        bad = await client.call_tool("search_filings", {"query": "revenue", "fiscal_year": 1800})
        assert bad.is_error
