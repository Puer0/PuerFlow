from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from typing import Any
from urllib.parse import urlparse

import httpx

from puerflow_worker.tools.base import Tool, ToolMetadata, ToolResult

_REQUESTS: dict[str, deque[float]] = defaultdict(deque)


class MCPHttpTool(Tool):
    def __init__(
        self,
        *,
        name: str,
        url: str,
        func_name: str,
        description: str = "MCP remote function",
        parameters: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        dangerous: bool = False,
        timeout_seconds: float = 10.0,
        rate_limit_per_minute: int = 60,
    ) -> None:
        self.url = url
        self.func_name = func_name
        self.headers = dict(headers or {})
        _validate_domain(url)
        self.metadata = ToolMetadata(
            name=name,
            description=description,
            category="mcp",
            source="mcp",
            timeout_seconds=timeout_seconds,
            dangerous=dangerous,
            rate_limit_per_minute=rate_limit_per_minute,
            parameters=parameters
            or {
                "type": "object",
                "properties": {
                    "args": {
                        "type": "object",
                        "description": "Arguments passed to the remote MCP function.",
                    }
                },
            },
        )

    async def execute(self, parameters: dict[str, Any]) -> ToolResult:
        if not _allow_rate(self.metadata.name, self.metadata.rate_limit_per_minute):
            return ToolResult(success=False, error="rate limit exceeded", metadata={"source": "mcp"})
        call_args = dict(parameters)
        if "args" in call_args and isinstance(call_args.get("args"), dict) and len(call_args) == 1:
            call_args = call_args["args"]
        try:
            async with httpx.AsyncClient(timeout=self.metadata.timeout_seconds) as client:
                response = await client.post(
                    self.url,
                    json={"function": self.func_name, "args": call_args},
                    headers=self.headers,
                )
                response.raise_for_status()
                try:
                    output: Any = response.json()
                except ValueError:
                    output = response.text
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=str(exc), metadata={"source": "mcp"})
        return ToolResult(
            success=True,
            output=output,
            text=output if isinstance(output, str) else str(output),
            metadata={"source": "mcp", "url": self.url, "function": self.func_name},
        )


def _validate_domain(url: str) -> None:
    allowed = [item.strip() for item in os.getenv("MCP_ALLOWED_DOMAINS", "localhost,127.0.0.1").split(",") if item.strip()]
    if "*" in allowed:
        return
    host = urlparse(url).hostname or ""
    if not any(host == item or host.endswith("." + item) for item in allowed):
        raise ValueError(f"URL host '{host}' is not allowed by MCP_ALLOWED_DOMAINS: {allowed}")


def _allow_rate(name: str, limit: int | None) -> bool:
    if not limit or limit <= 0:
        return True
    now = time.time()
    queue = _REQUESTS[name]
    while queue and queue[0] < now - 60:
        queue.popleft()
    if len(queue) >= limit:
        return False
    queue.append(now)
    return True
