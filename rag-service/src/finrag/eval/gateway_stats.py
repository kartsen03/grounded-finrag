"""Latency, tokens and cost per question, read from the gateway's audit log.

    python -m finrag.eval.gateway_stats --prefix test-best- --out results/answers/gateway_test_best.json

Every gateway call made while answering one question carries that question's request ID
(rag-service -> gateway), so grouping audit rows by request_id gives per-question totals:
model time summed over the embedding, re-ranking and chat calls, tokens, and cost.
"""

from __future__ import annotations

import argparse
import json
import os

import psycopg

from finrag import config, provenance
from finrag.eval.metrics import percentile
from finrag.retrieval.store import DEFAULT_DSN


def collect(prefix: str) -> dict:
    with psycopg.connect(os.environ.get("FINRAG_PG_DSN", DEFAULT_DSN)) as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT request_id, count(*), sum(latency_ms), sum(prompt_tokens), sum(completion_tokens), sum(cost_usd),
                   bool_or(cache_hit), count(*) FILTER (WHERE outcome <> 'ok'),
                   sum(latency_ms) FILTER (WHERE endpoint = '/v1/chat/completions')
            FROM gateway.audit_log WHERE request_id LIKE %s GROUP BY request_id""", (prefix + "%",))
        rows = cur.fetchall()
        cur.execute("""SELECT endpoint, count(*), percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms),
                              percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms)
                       FROM gateway.audit_log WHERE request_id LIKE %s GROUP BY endpoint""", (prefix + "%",))
        by_endpoint = {e: {"calls": n, "p50_ms": float(p50), "p95_ms": float(p95)} for e, n, p50, p95 in cur.fetchall()}
    if not rows:
        raise SystemExit(f"no audit rows with request_id prefix {prefix!r}")
    model_ms = [float(r[2]) for r in rows]
    chat_ms = [float(r[8] or 0) for r in rows]
    costs = [float(r[5]) for r in rows]
    return {
        "request_id_prefix": prefix,
        "questions": len(rows),
        "gateway_calls": sum(r[1] for r in rows),
        "calls_with_errors": sum(r[7] for r in rows),
        "questions_with_a_cache_hit": sum(1 for r in rows if r[6]),
        "model_time_per_question_ms": {"p50": percentile(model_ms, 0.5), "p95": percentile(model_ms, 0.95)},
        "chat_time_per_question_ms": {"p50": percentile(chat_ms, 0.5), "p95": percentile(chat_ms, 0.95)},
        "tokens_per_question": {"prompt_mean": round(sum(r[3] for r in rows) / len(rows), 1),
                                "completion_mean": round(sum(r[4] for r in rows) / len(rows), 1)},
        "cost_usd_per_question": {"mean": round(sum(costs) / len(costs), 8), "max": max(costs),
                                  "note": "local models are priced at 0 USD per 1k tokens in the gateway config"},
        "by_endpoint": by_endpoint,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    stats = collect(args.prefix)
    out = config.REPO_ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({**provenance.stamp(step="gateway_stats"), **stats}, indent=2) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
