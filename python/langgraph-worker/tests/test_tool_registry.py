from __future__ import annotations

import asyncio
import json

from puerflow_worker.events import ShannonEvent
from puerflow_worker.llm import CompletionClient, LLMResponse, LLMUsage
from puerflow_worker.runtime import TaskState
from puerflow_worker.sandbox import CommandResult, FileResult
from puerflow_worker.settings import WorkerSettings
from puerflow_worker.strategies.sample import SampleStrategy
from puerflow_worker.tools import build_default_registry
from puerflow_worker.tools.builtin import CalculatorTool
from puerflow_worker.tools.registry import ToolRegistry, _approval_matches, _binding_id, load_mcp_tools_from_json


class FakeSandbox:
    def __init__(self) -> None:
        self.writes: list[str] = []

    async def file_write(self, path, content, session_id="", user_id=""):
        self.writes.append(path)
        return FileResult(success=True, bytes_written=len(content or ""))

    async def execute_python(self, code, session_id="", user_id=""):
        return CommandResult(success=True, stdout="ok\n")

    async def file_list(self, path="", session_id="", user_id="", recursive=True):
        return []

    async def file_read(self, path, session_id="", user_id=""):
        return FileResult(success=True, content="")

    async def file_delete(self, path, session_id="", user_id=""):
        return FileResult(success=True)


class ToolLLM(CompletionClient):
    def __init__(self) -> None:
        super().__init__(mock=True)
        self.calls = 0

    async def generate(self, messages, temperature=0.2, tools=None):
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                content="",
                tool_calls=[{"id": "call_1", "name": "calculator", "arguments": {"expression": "2+2"}}],
                usage=LLMUsage(total_tokens=4),
            )
        return LLMResponse(content="the answer is 4", usage=LLMUsage(total_tokens=6))


async def test_registry_validates_and_audits():
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    missing = await registry.execute("calculator", {})
    assert missing.success is False
    assert "missing required" in (missing.error or "")
    ok = await registry.execute("calculator", {"expression": "1+2"})
    assert ok.success is True
    assert ok.text == "3"
    events = registry.audit_log()
    assert any(item["event_type"] == "tool_execution_blocked" for item in events)
    assert any(item["status"] == "success" for item in events)


async def test_register_mcp_from_json_and_execute(monkeypatch):
    class DummyResponse:
        content = b'{"ok": true}'
        text = '{"ok": true}'

        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True}

    class DummyClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            return DummyResponse()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", DummyClient)
    registry = ToolRegistry()
    load_mcp_tools_from_json(
        registry,
        json.dumps(
            {
                "name": "remote_search",
                "url": "http://127.0.0.1:9/mcp",
                "func_name": "search",
                "description": "demo mcp",
            }
        ),
    )
    tool = registry.get("remote_search")
    assert tool is not None
    assert tool.metadata.source == "mcp"
    result = await registry.execute("remote_search", {"q": "hello"})
    assert result.success is True


async def test_python_executor_staging_and_dangerous_approval():
    sandbox = FakeSandbox()
    registry = build_default_registry(sandbox, WorkerSettings(python_executor_dangerous=True))
    task = TaskState(workflow_id="wf-py", task_id="wf-py", strategy="sample", query="run")

    async def approve():
        await asyncio.sleep(0.05)
        task.approval = {"approved": True}
        task.approval_event.set()

    result, _ = await asyncio.gather(
        registry.execute("python_executor", {"code": "print(1)"}, task=task),
        approve(),
    )
    assert result.success is True
    assert any(path.startswith("staging/") for path in sandbox.writes)
    assert any(path.startswith("workspace/") for path in sandbox.writes)
    assert any(item["event_type"] == "tool_approval_required" for item in registry.audit_log()) is False
    assert task.allow_dangerous_tools is False


def test_approval_binding_rejects_other_tool():
    task = TaskState(workflow_id="wf", task_id="wf", strategy="sample", query="q", session={"session_id": "s1"})
    params = {"code": "print(1)", "session_id": "s1"}
    task.approval_request = {
        "approval_id": _binding_id("python_executor", params, "s1"),
        "tool_name": "python_executor",
        "parameters": params,
        "session_id": "s1",
    }
    task.approval = {"approved": True, "approval_id": task.approval_request["approval_id"]}
    assert _approval_matches(task, "python_executor", params)
    assert not _approval_matches(task, "file_delete", params)


async def test_sample_strategy_runs_tool_loop():
    events: list[ShannonEvent] = []

    async def emit(event: ShannonEvent) -> None:
        events.append(event)

    registry = ToolRegistry()
    registry.register(CalculatorTool())
    task = TaskState(workflow_id="wf-tool", task_id="wf-tool", strategy="sample", query="2+2")
    result = await SampleStrategy(ToolLLM(), tools=registry).run(task, emit)
    assert "4" in result.content
    assert any(item.type == "TOOL_INVOKED" for item in events)
    assert any(item.type == "TOOL_OBSERVATION" for item in events)
