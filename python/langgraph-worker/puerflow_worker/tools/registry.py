from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict, deque
from copy import deepcopy
from typing import Any, Awaitable, Callable

from puerflow_worker.events import ShannonEvent
from puerflow_worker.runtime import TaskState
from puerflow_worker.tools.base import Tool, ToolResult
from puerflow_worker.tools.mcp import MCPHttpTool

EmitFn = Callable[[ShannonEvent], Awaitable[None]]

_SECRET_MARKERS = ("authorization", "token", "secret", "password", "api_key", "apikey")


class ToolRegistry:
    def __init__(self, *, approval_timeout_seconds: float = 120.0) -> None:
        self._tools: dict[str, Tool] = {}
        self._audit: list[dict[str, Any]] = []
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self.approval_timeout_seconds = approval_timeout_seconds

    def register(self, tool: Tool, *, override: bool = True) -> None:
        if tool.metadata.name in self._tools and not override:
            raise ValueError(f"Tool already registered: {tool.metadata.name}")
        self._tools[tool.metadata.name] = tool

    def register_mcp_tool(
        self,
        *,
        name: str,
        url: str,
        func_name: str,
        description: str = "MCP remote function",
        parameters: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        dangerous: bool = False,
        override: bool = True,
    ) -> None:
        self.register(
            MCPHttpTool(
                name=name,
                url=url,
                func_name=func_name,
                description=description,
                parameters=parameters,
                headers=headers,
                dangerous=dangerous,
            ),
            override=override,
        )

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_tools(self, names: list[str] | None = None) -> list[Tool]:
        if names:
            return [self._tools[name] for name in names if name in self._tools]
        return list(self._tools.values())

    def openai_tools(self, names: list[str] | None = None) -> list[dict[str, Any]]:
        return [tool.openai_tool() for tool in self.list_tools(names) if tool.metadata.enabled]

    def audit_log(self) -> list[dict[str, Any]]:
        return list(self._audit)

    async def execute(
        self,
        name: str,
        parameters: dict[str, Any] | None = None,
        *,
        task: TaskState | None = None,
        emit: EmitFn | None = None,
        allow_dangerous: bool = False,
    ) -> ToolResult:
        tool = self.get(name)
        if tool is None:
            result = ToolResult(success=False, error="tool not found")
            self._record("tool_execution", name, "error", {"error": result.error})
            return result
        if not tool.metadata.enabled:
            return ToolResult(success=False, error="tool is disabled")

        params = deepcopy(parameters or {})
        if task is not None:
            session = task.session or {}
            params.setdefault("session_id", session.get("session_id") or task.workflow_id)
            params.setdefault("user_id", session.get("user_id") or "")
            params.setdefault("workflow_id", task.workflow_id)

        error = _validate_parameters(tool.metadata.parameters, params)
        if error:
            self._record("tool_execution_blocked", name, "invalid_params", {"error": error, "parameters": _redact(params)})
            return ToolResult(success=False, error=error)

        if tool.metadata.dangerous and not allow_dangerous and not (task and task.allow_dangerous_tools):
            approved = await self._wait_approval(tool.metadata.name, params, task=task, emit=emit)
            if not approved:
                self._record("tool_approval_required", name, "pending", {"parameters": _redact(params)})
                return ToolResult(
                    success=False,
                    error="tool requires approval before execution",
                    metadata={"approval_required": True, "tool_name": name},
                )

        if not self._allow_rate(name, tool.metadata.rate_limit_per_minute):
            self._record("tool_execution_blocked", name, "rate_limited", {"parameters": _redact(params)})
            return ToolResult(success=False, error="rate limit exceeded")

        if emit and task:
            await emit(
                ShannonEvent(
                    workflow_id=task.workflow_id,
                    type="TOOL_INVOKED",
                    agent_id=f"{task.strategy}-agent",
                    message=name,
                    payload={"tool": name, "parameters": _redact(params)},
                )
            )

        start = time.time()
        try:
            result = await asyncio.wait_for(tool.execute(params), timeout=tool.metadata.timeout_seconds)
        except TimeoutError:
            result = ToolResult(success=False, error="tool execution timed out")
        except Exception as exc:  # noqa: BLE001
            result = ToolResult(success=False, error=str(exc))
        result.execution_time_ms = result.execution_time_ms or int((time.time() - start) * 1000)
        result.metadata = {
            **(result.metadata or {}),
            "tool_name": name,
            "tool_source": tool.metadata.source,
        }
        self._record(
            "tool_execution",
            name,
            "success" if result.success else "error",
            {
                "parameters": _redact(params),
                "success": result.success,
                "error": result.error,
                "execution_time_ms": result.execution_time_ms,
            },
        )
        if emit and task:
            await emit(
                ShannonEvent(
                    workflow_id=task.workflow_id,
                    type="TOOL_OBSERVATION" if result.success else "TOOL_ERROR",
                    agent_id=f"{task.strategy}-agent",
                    message=(result.text or result.error or "")[:2000],
                    payload={"tool": name, "success": result.success},
                )
            )
        return result

    async def _wait_approval(
        self,
        tool_name: str,
        parameters: dict[str, Any],
        *,
        task: TaskState | None,
        emit: EmitFn | None,
    ) -> bool:
        if task is None:
            return False
        task.status = "waiting_approval"
        task.approval_event.clear()
        task.approval = None
        if emit:
            await emit(
                ShannonEvent(
                    workflow_id=task.workflow_id,
                    type="WORKFLOW_PAUSED",
                    agent_id="langgraph-worker",
                    message=f"waiting for approval: {tool_name}",
                    payload={"tool": tool_name, "parameters": _redact(parameters)},
                )
            )
        try:
            await asyncio.wait_for(task.approval_event.wait(), timeout=self.approval_timeout_seconds)
        except TimeoutError:
            return False
        approved = bool((task.approval or {}).get("approved"))
        if approved:
            task.allow_dangerous_tools = True
            task.status = "running"
        return approved

    def _allow_rate(self, name: str, limit: int | None) -> bool:
        if not limit or limit <= 0:
            return True
        now = time.time()
        queue = self._requests[name]
        while queue and queue[0] < now - 60:
            queue.popleft()
        if len(queue) >= limit:
            return False
        queue.append(now)
        return True

    def _record(self, event_type: str, tool_name: str, status: str, data: dict[str, Any]) -> None:
        self._audit.append(
            {
                "event_type": event_type,
                "tool_name": tool_name,
                "status": status,
                "data": data,
                "ts": time.time(),
            }
        )


def _validate_parameters(schema: dict[str, Any] | None, params: dict[str, Any]) -> str | None:
    if not schema:
        return None
    required = schema.get("required") or []
    properties = schema.get("properties") or {}
    for name in required:
        if name not in params or params[name] in (None, ""):
            return f"missing required parameter: {name}"
    for name, spec in properties.items():
        if name not in params or not isinstance(spec, dict):
            continue
        expected = spec.get("type")
        value = params[name]
        if expected == "string" and not isinstance(value, str):
            return f"parameter {name} must be a string"
        if expected == "integer" and not isinstance(value, int):
            return f"parameter {name} must be an integer"
        if expected == "number" and not isinstance(value, (int, float)):
            return f"parameter {name} must be a number"
        if expected == "object" and not isinstance(value, dict):
            return f"parameter {name} must be an object"
    return None


def _redact(payload: dict[str, Any]) -> dict[str, Any]:
    redacted = {}
    for key, value in payload.items():
        lowered = str(key).lower()
        if any(marker in lowered for marker in _SECRET_MARKERS):
            redacted[key] = "***"
        else:
            redacted[key] = value
    return redacted


def load_mcp_tools_from_json(registry: ToolRegistry, raw: str) -> None:
    text = (raw or "").strip()
    if not text:
        return
    items = json.loads(text)
    if isinstance(items, dict):
        items = [items]
    for item in items:
        registry.register_mcp_tool(
            name=str(item["name"]),
            url=str(item["url"]),
            func_name=str(item.get("func_name") or item.get("function") or item["name"]),
            description=str(item.get("description") or "MCP remote function"),
            parameters=item.get("parameters"),
            headers=item.get("headers"),
            dangerous=bool(item.get("dangerous")),
        )
