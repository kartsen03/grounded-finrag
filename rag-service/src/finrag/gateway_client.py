"""Client for the LLM gateway: the rag-service's only way to reach any model.

Every call carries the API key and an X-Request-Id; the ID is generated per question
upstream and passed down, so one ID ties the rag-service log, the gateway's audit log
and the provider call together.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass

import httpx
import numpy as np

DEFAULT_URL = "http://127.0.0.1:8080"
DEV_KEY = "dev-rag-service-key"  # local development key; its hash is the gateway's default
EMBED_BATCH = 64


@dataclass
class ChatReply:
    content: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    provider: str
    request_id: str
    cache_hit: bool = False


class GatewayClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None, timeout: float = 300.0):
        self.base_url = base_url or os.environ.get("GATEWAY_URL", DEFAULT_URL)
        self.api_key = api_key or os.environ.get("GATEWAY_API_KEY", DEV_KEY)
        self._http = httpx.Client(base_url=self.base_url, timeout=timeout,
                                  headers={"X-API-Key": self.api_key})

    @staticmethod
    def new_request_id() -> str:
        return uuid.uuid4().hex

    def _post(self, path: str, body: dict, request_id: str | None) -> dict:
        rid = request_id or self.new_request_id()
        resp = self._http.post(path, json=body, headers={"X-Request-Id": rid})
        resp.raise_for_status()
        return resp.json()

    def embed(self, texts: list[str], model: str, request_id: str | None = None) -> np.ndarray:
        """Embeddings as a float32 matrix (rows L2-normalized by the model server)."""
        out = []
        for i in range(0, len(texts), EMBED_BATCH):
            data = self._post("/v1/embeddings", {"model": model, "input": texts[i:i + EMBED_BATCH]}, request_id)
            out.extend(data["embeddings"])
        return np.asarray(out, dtype=np.float32)

    def rerank(self, query: str, documents: list[str], model: str, request_id: str | None = None) -> list[float]:
        data = self._post("/v1/rerank", {"model": model, "query": query, "documents": documents}, request_id)
        return data["scores"]

    def chat(self, messages: list[dict], model: str, request_id: str | None = None, temperature: float = 0.0,
             max_tokens: int | None = None, seed: int | None = 0, json_schema: dict | None = None) -> ChatReply:
        body: dict = {"model": model, "messages": messages, "temperature": temperature, "seed": seed}
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if json_schema is not None:
            body["response_format"] = json_schema
        data = self._post("/v1/chat/completions", body, request_id)
        return ChatReply(content=data["message"]["content"], prompt_tokens=data["usage"]["prompt_tokens"],
                         completion_tokens=data["usage"]["completion_tokens"], latency_ms=data["latency_ms"],
                         provider=data["provider"], request_id=data["request_id"],
                         cache_hit=bool(data.get("cache_hit", False)))

    def close(self) -> None:
        self._http.close()
