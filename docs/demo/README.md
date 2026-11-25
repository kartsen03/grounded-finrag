# MCP demo transcripts (Claude Code)

Three real questions asked through Claude Code with the grounded-finrag MCP server connected over
stdio. Each transcript has every tool call with its arguments, every tool result, and the model's
reply. The `.md` files shorten long lists for reading. The `.json` files hold the full tool results.

| Transcript | What it shows |
|---|---|
| [q1-3m-capex](q1-3m-capex.md) | One `answer_question` call with `company: "3M"`; cited answer, $1,577 million [3M_2018_10K, p.60] |
| [q2-amd-revenue](q2-amd-revenue.md) | `list_filings` and `answer_question` called in parallel; two AMD filings listed, FY2022 revenue $23,601 million [AMD_2022_10K, p.68] |
| [q3-apple-not-indexed](q3-apple-not-indexed.md) | A company that is not indexed: both tools return `unknown_company`, the model checks `list_filings` and reports there is no evidence |
| [q3-before-fix](q3-before-fix.md) | The same question at commit `be3a86e`, before a bug fix (below) |

**Setup for all runs.** Claude Code 2.1.218, model `claude-sonnet-5-5`, MCP SDK `mcp==2.3.0` on the
server, run date 2026-11-25 (UTC). Server commit `5345522`, except `q3-before-fix` at `be3a86e`.
The local stack was the same as for the latency numbers in `results/mcp/latency.json`: gateway cache
off, model server on CPU, `qwen2.5:7b-instruct-q4_K_M` in Ollama on an RTX 3060 Laptop GPU. The
client could use only the three MCP tools (`--tools ""` disables the built-in ones):

```bash
export GATEWAY_API_KEY=...            # the mcp-server client key; never written to a file
claude -p "<question>" --output-format stream-json --verbose \
  --mcp-config .mcp.json --strict-mcp-config --tools "" \
  --allowedTools mcp__grounded-finrag__search_filings mcp__grounded-finrag__answer_question \
                 mcp__grounded-finrag__list_filings \
  --model claude-sonnet-5-5 < /dev/null > q.jsonl
python scripts/render_mcp_transcript.py q.jsonl docs/demo/<name> --question "<question>" \
  --server-commit <sha> --mcp-sdk 2.3.0 --date <yyyy-mm-dd>
```

Set `MCP_CONNECTION_NONBLOCKING=false` for `claude -p`. Without it, the first attempt began
before the server finished connecting, and the model had no tools. That attempt is not kept.

## The bug the real client found

The SDK-client tests ran tools one at a time. Claude Code does not: in q3 it called
`search_filings` and `answer_question` in parallel. Both validated the company argument, which
loads the filing list into a cache. Both found the cache empty and both filled it, so the next
`list_filings` reported **168** filings instead of 84 (see `q3-before-fix`). Commit `96ee85d`
guards the fill with a lock and adds a regression test. That test fails on the old code and passes
on the new. The other transcripts and the latency file were re-run after the fix.

## What the transcripts do not show

- The model's prose is the client's own and is not checked by the server. In q3 the model added a
  figure for Apple "from my own general knowledge," labeled as unverified. It also put Amazon in its list of
  companies with fiscal 2022 10-Ks, while noting that only Amazon's 2017 and 2019 filings are
  indexed. Only the tool results are grounded.
- Each question was asked once. The durations in the headers are single runs and include the
  model's own turns. They are not latency statistics; `results/mcp/latency.json` has those.
- Claude Desktop and every non-Claude client were not tested.
