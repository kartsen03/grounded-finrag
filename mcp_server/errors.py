"""Map backend failures to structured, model-readable tool errors (never stack traces).

Every failure becomes a ToolError whose message is a small JSON object:
    {"error": {"code": "...", "message": "...", "retryable": true|false}}
The MCP client receives it as an is_error result. Details go to the server's stderr log, never
secrets: API keys are not part of any exception message produced here.
"""

from __future__ import annotations

import json
import logging

import httpx
import psycopg
from mcp.server.mcpserver.exceptions import ToolError

log = logging.getLogger("finrag.mcp")


class ToolFailure(Exception):
    """An anticipated failure raised by tool code itself (e.g. an unknown company)."""

    def __init__(self, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.code, self.message, self.retryable = code, message, retryable


def tool_error(code: str, message: str, retryable: bool) -> ToolError:
    return ToolError(json.dumps({"error": {"code": code, "message": message, "retryable": retryable}}))


def classify(exc: BaseException) -> ToolError:
    if isinstance(exc, ToolFailure):
        return tool_error(exc.code, exc.message, exc.retryable)
    if isinstance(exc, TimeoutError):
        return tool_error("timeout", "The backend did not respond in time.", True)
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == 429:
            wait = exc.response.headers.get("Retry-After", "60")
            return tool_error("rate_limited", f"Gateway rate limit reached; retry after {wait} s.", True)
        if status in (401, 403):
            return tool_error("gateway_unauthorized",
                              "The gateway rejected the API key (check GATEWAY_API_KEY).", False)
        if status >= 500:
            return tool_error("gateway_error", f"The gateway or a model provider failed (HTTP {status}).", True)
        return tool_error("gateway_rejected", f"The gateway rejected the request (HTTP {status}).", False)
    if isinstance(exc, httpx.TimeoutException):
        return tool_error("timeout", "The gateway did not respond in time.", True)
    if isinstance(exc, httpx.TransportError):
        return tool_error("backend_unavailable", "The LLM gateway is not reachable.", True)
    if isinstance(exc, psycopg.OperationalError):
        return tool_error("database_unavailable", "The vector database is not reachable.", True)
    log.error("unexpected tool failure: %s", type(exc).__name__, exc_info=exc)
    return tool_error("internal_error", "Unexpected server error; see the MCP server log.", False)
