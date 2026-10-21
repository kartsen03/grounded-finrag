from fastapi.testclient import TestClient

from finrag import api


class FakeAnswerer:
    def answer(self, question, cfg, request_id=None):
        return {"answer": "Capex was 1,577. [3M_2018_10K, p.60]", "abstained": False, "mode": "grounded",
                "citations": [["3M_2018_10K", 60]], "support": 0.9, "timings_ms": {"total": 12.0}}


def test_answer_endpoint_propagates_request_id_and_citations(monkeypatch):
    app = api.app
    app.router.lifespan_context = _no_lifespan
    api.state.update({"answerer": FakeAnswerer(), "answer_config": None})
    with TestClient(app) as client:
        resp = client.post("/answer", json={"question": "What was 3M capex in FY2018?"},
                           headers={"X-Request-Id": "abc-123"})
    assert resp.status_code == 200
    assert resp.headers["X-Request-Id"] == "abc-123"
    body = resp.json()
    assert body["request_id"] == "abc-123"
    assert body["citations"] == [{"doc_name": "3M_2018_10K", "page": 60}]


def test_unsafe_request_id_is_replaced():
    api.app.router.lifespan_context = _no_lifespan
    with TestClient(api.app) as client:
        resp = client.get("/health", headers={"X-Request-Id": "bad id\nx"})
    assert resp.headers["X-Request-Id"] != "bad id\nx" and len(resp.headers["X-Request-Id"]) == 32


from contextlib import asynccontextmanager  # noqa: E402


@asynccontextmanager
async def _no_lifespan(_app):
    yield
