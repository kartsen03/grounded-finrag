"""Grounded answering: retrieve -> generate (JSON) -> verify -> repair once -> answer or abstain.

Modes
  naive     free-text answer with inline citations; nothing is verified (baseline).
  grounded  claims with source IDs; every ID must name a source that was actually provided.
  extract   extract-then-compute: the model returns cited line items and a formula, Python
            checks every value against its cited page and computes the result.
  auto      extract for numeric questions (see classify.py), grounded otherwise.

Abstention: the model may declare insufficient evidence; independently, `support` (the best
cross-encoder relevance among the context chunks) is recorded for every answer, and answers
below a threshold tuned on dev are replaced by "insufficient evidence".
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass

from finrag import corpus
from finrag.answer import classify, prompts
from finrag.answer.numbers import FormulaError, evaluate, grounded, numbers_in
from finrag.gateway_client import GatewayClient
from finrag.retrieval.pipeline import RERANK_ALIAS, RetrievalConfig, Retriever, chunk_index

CHAT_ALIAS = "local-chat"
INSUFFICIENT = "Insufficient evidence in the retrieved filings to answer this question."
MAX_TOKENS = 600  # answers are short; a cap stops degenerate repetition early
ORACLE_MAX_CHUNKS = 8


@dataclass(frozen=True)
class AnswerConfig:
    name: str
    retrieval: RetrievalConfig | None  # None -> oracle (gold evidence pages)
    mode: str = "auto"  # naive | grounded | extract | auto
    context_k: int = 5
    repair: bool = True
    abstain_threshold: float | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["retrieval"] = self.retrieval.to_dict() if self.retrieval else "oracle"
        return d


class Answerer:
    def __init__(self, gateway: GatewayClient, retriever: Retriever):
        self.gateway = gateway
        self.retriever = retriever

    # ------------------------------------------------------------------ context

    def _sources(self, question: str, cfg: AnswerConfig, gold: set[tuple[str, int]] | None,
                 request_id: str, timings: dict) -> tuple[list[dict], dict | None]:
        t0 = time.perf_counter()
        route = None
        if cfg.retrieval is None:
            idx = chunk_index("structure")
            chunks = sorted((c for c in idx.chunks if (c["doc_name"], c["page_idx"]) in (gold or set())),
                            key=lambda c: (c["doc_name"], c["page_idx"], c["chunk_id"]))[:ORACLE_MAX_CHUNKS]
        else:
            res = self.retriever.retrieve(question, cfg.retrieval, request_id=request_id)
            chunks = [h.chunk for h in res.hits][:cfg.context_k]
            timings.update({f"retrieval_{k}": v for k, v in res.timings_ms.items()})
            if res.route is not None:
                route = {"rule": res.route.rule, "companies": sorted(res.route.companies)}
        timings["retrieval"] = round((time.perf_counter() - t0) * 1000, 2)
        sources = [{"id": f"S{i + 1}", "chunk_id": c["chunk_id"], "doc_name": c["doc_name"],
                    "page_idx": c["page_idx"], "page": c["page_idx"] + 1, "section": c["section"],
                    "text": c["text"], "embed_text": c["embed_text"]} for i, c in enumerate(chunks)]
        return sources, route

    def _support(self, question: str, sources: list[dict], request_id: str, timings: dict) -> float | None:
        if not sources:
            return None
        t0 = time.perf_counter()
        scores = self.gateway.rerank(question, [s["embed_text"] for s in sources], RERANK_ALIAS, request_id)
        timings["support_score"] = round((time.perf_counter() - t0) * 1000, 2)
        return max(scores)

    # ------------------------------------------------------------------ generation

    def _chat(self, messages: list[dict], schema: dict | None, request_id: str, usage: dict) -> str:
        reply = self.gateway.chat(messages, CHAT_ALIAS, request_id=request_id, temperature=0.0, seed=0,
                                  max_tokens=MAX_TOKENS, json_schema=schema)
        usage["prompt_tokens"] += reply.prompt_tokens
        usage["completion_tokens"] += reply.completion_tokens
        usage["llm_calls"] += 1
        usage["llm_ms"] += reply.latency_ms
        usage["cache_hits"] += int(reply.cache_hit)
        return reply.content

    def answer(self, question: str, cfg: AnswerConfig, gold: set[tuple[str, int]] | None = None,
               request_id: str | None = None) -> dict:
        rid = request_id or GatewayClient.new_request_id()
        timings: dict[str, float] = {}
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "llm_calls": 0, "llm_ms": 0, "cache_hits": 0}
        start = time.perf_counter()
        sources, route = self._sources(question, cfg, gold, rid, timings)
        support = self._support(question, sources, rid, timings)
        mode = cfg.mode if cfg.mode != "auto" else ("extract" if classify.is_numeric(question) else "grounded")
        record = {"question": question, "config": cfg.name, "mode": mode, "request_id": rid, "route": route,
                  "support": support, "sources": [{k: s[k] for k in ("id", "chunk_id", "doc_name", "page", "page_idx")}
                                                  for s in sources]}
        t0 = time.perf_counter()
        if not sources:
            record.update(_abstain("no_sources"))
        elif mode == "naive":
            text = self._chat([{"role": "system", "content": prompts.NAIVE_SYSTEM},
                               {"role": "user", "content": prompts.user_message(question, sources)}], None, rid, usage)
            record.update({"answer": text, "abstained": False, "citations": [], "verification": None})
        else:
            record.update(self._structured(question, mode, sources, cfg.repair, rid, usage))
        timings["generation"] = round((time.perf_counter() - t0) * 1000, 2)

        if (not record["abstained"] and cfg.abstain_threshold is not None and support is not None
                and support < cfg.abstain_threshold):
            record["answer_before_abstention"] = record["answer"]
            record.update(_abstain("weak_retrieval_support"))
        timings["total"] = round((time.perf_counter() - start) * 1000, 2)
        record.update({"timings_ms": timings, "usage": usage})
        return record

    def _structured(self, question: str, mode: str, sources: list[dict], repair: bool, rid: str,
                    usage: dict) -> dict:
        system, schema = ((prompts.EXTRACT_SYSTEM, prompts.EXTRACT_SCHEMA) if mode == "extract"
                          else (prompts.GROUNDED_SYSTEM, prompts.GROUNDED_SCHEMA))
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": prompts.user_message(question, sources)}]
        by_id = {s["id"]: s for s in sources}
        attempts = []
        for attempt in range(2 if repair else 1):
            raw = self._chat(messages, schema, rid, usage)
            result = (verify_extract if mode == "extract" else verify_grounded)(raw, by_id)
            attempts.append({"raw": raw, "errors": result["errors"]})
            if not result["errors"]:
                break
            messages += [{"role": "assistant", "content": raw},
                         {"role": "user", "content": prompts.repair_message(result["errors"])}]
        verification = {"passed": not result["errors"], "attempts": len(attempts),
                        "repaired": len(attempts) > 1 and not result["errors"],
                        "first_errors": attempts[0]["errors"], "final_errors": result["errors"],
                        "ungrounded_numbers": result.get("ungrounded_numbers", [])}
        if result.get("insufficient"):
            return {**_abstain("model_insufficient_evidence"), "verification": verification, "raw": attempts}
        if result["errors"]:
            return {**_abstain("verification_failed"), "verification": verification, "raw": attempts}
        return {"answer": result["answer"], "abstained": False, "citations": result["citations"],
                "computation": result.get("computation"), "verification": verification, "raw": attempts}


def _abstain(reason: str) -> dict:
    return {"answer": INSUFFICIENT, "abstained": True, "abstain_reason": reason, "citations": []}


def _cite(src: dict) -> str:
    return f"[{src['doc_name']}, p.{src['page']}]"


def _source_id(value: object) -> str:
    """Models often write "[S2]" or " s2"; the ID itself is what matters."""
    return str(value).strip().strip("[]").strip().upper()


def _parse(raw: str) -> tuple[dict | None, list[str]]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None, ["the reply is not valid JSON"]
    if not isinstance(data, dict):
        return None, ["the reply must be a JSON object"]
    return data, []


def verify_grounded(raw: str, by_id: dict[str, dict]) -> dict:
    data, errors = _parse(raw)
    if data is None:
        return {"errors": errors}
    if data.get("insufficient_evidence"):
        return {"errors": [], "insufficient": True}
    claims = data.get("claims") or []
    if not claims:
        errors.append("there are no claims; every answer needs at least one cited claim")
    citations, rendered, ungrounded = [], [], []
    for i, claim in enumerate(claims, start=1):
        ids = [_source_id(x) for x in claim.get("source_ids") or []]
        if not ids:
            errors.append(f"claim {i} cites no source")
        bad = [x for x in ids if x not in by_id]
        if bad:
            errors.append(f"claim {i} cites {', '.join(bad)}, which were not provided (valid: {', '.join(by_id)})")
        good = [by_id[x] for x in ids if x in by_id]
        cited_text = "\n".join(s["text"] for s in good)
        for value in numbers_in(claim.get("statement", "")):
            if not (1900 <= value <= 2100 and value.is_integer()) and not grounded(value, cited_text):
                ungrounded.append({"claim": i, "value": value})
        for s in good:
            if (s["doc_name"], s["page"]) not in citations:
                citations.append((s["doc_name"], s["page"]))
        rendered.append(f"{claim.get('statement', '').strip()} {' '.join(_cite(s) for s in good)}".strip())
    answer = (data.get("answer") or "").strip()
    full = answer + ("\n\n" + "\n".join(f"- {r}" for r in rendered) if rendered else "")
    return {"errors": errors, "answer": full, "citations": [list(c) for c in citations],
            "ungrounded_numbers": ungrounded}


def verify_extract(raw: str, by_id: dict[str, dict]) -> dict:
    data, errors = _parse(raw)
    if data is None:
        return {"errors": errors}
    if data.get("insufficient_evidence"):
        return {"errors": [], "insufficient": True}
    inputs = data.get("inputs") or []
    if not inputs:
        errors.append("no inputs were extracted")
    variables, lines, citations = {}, [], []
    for item in inputs:
        name, sid, value = item.get("name", ""), _source_id(item.get("source_id", "")), item.get("value")
        if not name.isidentifier():
            errors.append(f"input name {name!r} must be a snake_case identifier")
            continue
        if sid not in by_id:
            errors.append(f"input {name} cites {sid!r}, which was not provided (valid: {', '.join(by_id)})")
            continue
        if not isinstance(value, (int, float)):
            errors.append(f"input {name} has no numeric value")
            continue
        src = by_id[sid]
        if not grounded(float(value), src["text"]):
            errors.append(f"input {name} = {value} does not appear in {sid}; copy the value exactly as printed")
            continue
        variables[name] = float(value)
        lines.append(f"{name} = {value:g} ({item.get('line_item', '')}, {item.get('period', '')}) {_cite(src)}")
        if (src["doc_name"], src["page"]) not in citations:
            citations.append((src["doc_name"], src["page"]))
    result = None
    formula = (data.get("formula") or "").strip()
    if not errors:
        try:
            result = evaluate(formula, variables)
        except FormulaError as e:
            errors.append(str(e))
    if errors:
        return {"errors": errors}
    unit = (data.get("unit") or "").strip()
    metric = (data.get("metric") or "result").strip()
    answer = (f"{metric}: {result:,.2f} {unit}".strip() + f"\nComputed as {formula}, where:\n"
              + "\n".join(f"- {line}" for line in lines))
    return {"errors": [], "answer": answer, "citations": [list(c) for c in citations],
            "computation": {"metric": metric, "formula": formula, "inputs": variables, "result": result,
                            "unit": unit}}


def gold_pages(qid: str) -> set[tuple[str, int]]:
    return corpus.evidence_pages(corpus.questions()[qid])
