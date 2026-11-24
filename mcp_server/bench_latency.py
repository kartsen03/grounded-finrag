"""Per-tool latency of the MCP server over stdio, measured from an MCP client.

    GATEWAY_API_KEY=... python mcp_server/bench_latency.py [--calls 20] [--out results/mcp/latency.json]

Starts the server as a subprocess (the same stdio transport Claude Code uses), makes one warm-up
call per tool (reported separately as the cold call), then `--calls` timed calls per tool.
search_filings and answer_question use the first dev-split FinanceBench questions, one distinct
question per call; list_filings takes no arguments. Each time is the client-side round trip of
`call_tool`: JSON-RPC over stdio plus the server's work (retrieval, gateway calls, LLM). It does not
include any time a chat client spends deciding which tool to call.

The results file stores question IDs only (FinanceBench text is CC BY-NC and is not committed).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import time
from pathlib import Path

import anyio
from mcp import Client
from mcp.client.stdio import StdioServerParameters

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "rag-service" / "src"))

from finrag import corpus, provenance  # noqa: E402

SERVER = ROOT / "mcp_server" / "server.py"


def nearest_rank(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(pct / 100 * len(ordered)) - 1)]


def summarize(calls: list[dict]) -> dict:
    ms = [c["ms"] for c in calls]
    return {"n": len(ms), "p50_ms": round(statistics.median(ms), 1), "p95_ms": round(nearest_rank(ms, 95), 1),
            "min_ms": round(min(ms), 1), "max_ms": round(max(ms), 1), "mean_ms": round(statistics.fmean(ms), 1),
            "errors": sum(c["is_error"] for c in calls)}


async def timed(client: Client, tool: str, args: dict, qid: str | None) -> dict:
    start = time.perf_counter()
    res = await client.call_tool(tool, args)
    ms = (time.perf_counter() - start) * 1000
    out = res.structured_content or {}
    rec = {"tool": tool, "financebench_id": qid, "ms": round(ms, 1), "is_error": bool(res.is_error)}
    if tool == "search_filings":
        rec["status"] = out.get("status")
    elif tool == "answer_question":
        rec["abstained"] = out.get("abstained")
    return rec


async def bench(calls: int) -> dict:
    qs = corpus.questions()
    ids = sorted(corpus.split()["dev"])[: calls + 1]  # the extra one is the warm-up question
    warm_id, timed_ids = ids[0], ids[1:]
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER)], env=dict(os.environ), cwd=str(ROOT))
    async with Client(params, read_timeout_seconds=360) as client:
        cold = [await timed(client, "list_filings", {}, None),
                await timed(client, "search_filings", {"query": qs[warm_id]["question"]}, warm_id),
                await timed(client, "answer_question", {"question": qs[warm_id]["question"]}, warm_id)]
        runs = {"list_filings": [await timed(client, "list_filings", {}, None) for _ in range(calls)]}
        runs["search_filings"] = [await timed(client, "search_filings", {"query": qs[q]["question"]}, q)
                                  for q in timed_ids]
        runs["answer_question"] = [await timed(client, "answer_question", {"question": qs[q]["question"]}, q)
                                   for q in timed_ids]
    return {"cold_first_call": cold, "summary": {t: summarize(c) for t, c in runs.items()}, "calls": runs}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--calls", type=int, default=20)
    parser.add_argument("--out", type=Path, default=ROOT / "results" / "mcp" / "latency.json")
    parser.add_argument("--setup-note", default="", help="free-text description of the local stack, recorded as given")
    args = parser.parse_args()
    if not os.environ.get("GATEWAY_API_KEY"):
        print("GATEWAY_API_KEY is not set", file=sys.stderr)
        return 2
    started = time.time()
    result = anyio.run(bench, args.calls)
    mcp_dirty = provenance._run(["git", "status", "--porcelain", "--", "mcp_server"])
    record = provenance.stamp(
        "mcp", "mcp-types", "anyio", "httpx",
        step="mcp-latency", transport="stdio", client="mcp Python SDK Client (in this script)",
        method="client-side call_tool round trip, sequential calls; p95 by nearest rank",
        mcp_server_dirty=bool(mcp_dirty), wall_seconds=round(time.time() - started, 1),
        setup_note=args.setup_note, **result)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    for tool, s in record["summary"].items():
        print(f"{tool:16s} n={s['n']} p50={s['p50_ms']} ms p95={s['p95_ms']} ms errors={s['errors']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
