"""Turn a Claude Code `--output-format stream-json` log into a demo transcript (Markdown + JSON).

    python scripts/render_mcp_transcript.py runs/mcp_demo/q1.jsonl docs/demo/q1 --server-commit <sha>

Keeps only what a reader needs to check the run: the question, every tool call with its arguments,
every tool result, the model's text, and run metadata (client version, model, MCP server status,
duration, turns). Session IDs, paths, the plugin and skill lists, and cost estimates are dropped.
The JSON file holds tool results in full; the Markdown shortens long evidence text for reading.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

PREVIEW_CHARS = 400
LIST_PREVIEW = 4


def _parse(content) -> object:
    """Tool results arrive as text blocks; the server's structured output is JSON text."""
    if isinstance(content, list):
        texts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
        content = "\n".join(texts)
    try:
        return json.loads(content)
    except (TypeError, ValueError):
        return content


def load(path: Path) -> dict:
    run = {"steps": []}
    for line in path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        kind = event.get("type")
        if kind == "system" and event.get("subtype") == "init":
            run["client"] = f"Claude Code {event.get('claude_code_version')}"
            run["model"] = event.get("model")
            run["mcp_tools_available"] = sorted(t for t in event.get("tools", []) if t.startswith("mcp__"))
            run["other_tools_available"] = sorted(t for t in event.get("tools", []) if not t.startswith("mcp__"))
        elif kind == "assistant":
            for block in event["message"]["content"]:
                if block["type"] == "text" and block["text"].strip():
                    run["steps"].append({"assistant_text": block["text"]})
                elif block["type"] == "tool_use":
                    run["steps"].append({"tool_call": {"id": block["id"], "name": block["name"], "input": block["input"]}})
        elif kind == "user":
            content = event["message"]["content"]
            for block in content if isinstance(content, list) else []:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    run["steps"].append({"tool_result": {"id": block["tool_use_id"], "is_error": bool(block.get("is_error")),
                                                         "content": _parse(block.get("content"))}})
        elif kind == "result":
            run["outcome"] = {"subtype": event.get("subtype"), "duration_ms": event.get("duration_ms"),
                              "num_turns": event.get("num_turns"), "final_text": event.get("result")}
    return run


def _short(value):
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k == "text" and isinstance(v, str) and len(v) > PREVIEW_CHARS:
                out[k] = v[:PREVIEW_CHARS] + f" ... [{len(v) - PREVIEW_CHARS} more characters in the JSON transcript]"
            else:
                out[k] = _short(v)
        return out
    if isinstance(value, list):
        if len(value) > LIST_PREVIEW and all(isinstance(v, dict) for v in value):
            return [_short(v) for v in value[:LIST_PREVIEW]] + [f"... {len(value) - LIST_PREVIEW} more in the JSON transcript"]
        return [_short(v) for v in value]
    return value


def markdown(run: dict, question: str, meta: dict) -> str:
    lines = [f"# Demo: {question}", "",
             "| | |", "|---|---|",
             f"| Client | {run.get('client')} (`claude -p`, stream-json) |",
             f"| Model | `{run.get('model')}` |",
             f"| MCP server | grounded-finrag over stdio, commit `{meta['server_commit']}` |",
             f"| MCP SDK (server) | mcp {meta['mcp_sdk']} |",
             f"| Tools the model could use | {', '.join(f'`{t}`' for t in run.get('mcp_tools_available', []))}"
             f"{' (no built-in tools)' if not run.get('other_tools_available') else ''} |",
             f"| Run date (UTC) | {meta['date']} |",
             f"| Duration | {run['outcome']['duration_ms'] / 1000:.1f} s, {run['outcome']['num_turns']} turns |", "",
             "## User", "", f"> {question}", ""]
    n = 0
    for step in run["steps"]:
        if "assistant_text" in step:
            lines += ["## Assistant", "", step["assistant_text"].strip(), ""]
        elif "tool_call" in step:
            n += 1
            call = step["tool_call"]
            lines += [f"## Tool call {n}: `{call['name']}`", "", "```json", json.dumps(call["input"], indent=2), "```", ""]
        elif "tool_result" in step:
            res = step["tool_result"]
            label = "error result" if res["is_error"] else "result"
            body = res["content"]
            text = json.dumps(_short(body), indent=2, ensure_ascii=False) if not isinstance(body, str) else body
            lines += [f"### Tool {label}", "", "```json" if not isinstance(body, str) else "```", text, "```", ""]
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("log", type=Path)
    parser.add_argument("out_stem", type=Path)
    parser.add_argument("--question", required=True)
    parser.add_argument("--server-commit", required=True)
    parser.add_argument("--mcp-sdk", required=True)
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    run = load(args.log)
    meta = {"server_commit": args.server_commit, "mcp_sdk": args.mcp_sdk, "date": args.date}
    args.out_stem.parent.mkdir(parents=True, exist_ok=True)
    args.out_stem.with_suffix(".json").write_text(
        json.dumps({"question": args.question, **meta, **run}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    args.out_stem.with_suffix(".md").write_text(markdown(run, args.question, meta), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
