from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from puerflow_worker.events import ShannonEvent
from puerflow_worker.llm import CompletionClient, LLMResponse
from puerflow_worker.runtime import TaskState
from puerflow_worker.budget import raise_if_cancelled, raise_if_over_budget
from puerflow_worker.sandbox import SandboxClient
from puerflow_worker.tools import complete_turn, maybe_run_sandbox
from puerflow_worker.tools.registry import ToolRegistry

try:
    from langgraph.graph import END, StateGraph
except Exception:  # noqa: BLE001
    END = None
    StateGraph = None

EmitFn = Callable[[ShannonEvent], Awaitable[None]]


def split_subtasks(query: str) -> list[str]:
    raw = [part.strip() for part in query.replace("；", ";").replace("和", ";").split(";") if part.strip()]
    if len(raw) >= 2:
        return raw[:4]
    return [f"Analyze: {query}", f"Answer: {query}"]


def planned_subtasks(task: TaskState) -> list[dict[str, Any]]:
    raw = (task.context or {}).get("preplanned_subtasks") or []
    steps: list[dict[str, Any]] = []
    if isinstance(raw, list):
        for index, item in enumerate(raw, start=1):
            if isinstance(item, str):
                steps.append({"id": str(index), "description": item, "dependencies": [], "suggested_tools": []})
                continue
            if not isinstance(item, dict):
                continue
            deps = item.get("dependencies") or []
            tools = item.get("suggested_tools") or []
            steps.append(
                {
                    "id": str(item.get("id") or index),
                    "description": str(item.get("description") or item.get("name") or task.query),
                    "dependencies": [str(dep) for dep in deps],
                    "suggested_tools": [str(name) for name in tools],
                    "tool_parameters": item.get("tool_parameters") or {},
                }
            )
    if steps:
        return steps
    return [
        {"id": str(index), "description": part, "dependencies": [], "suggested_tools": []}
        for index, part in enumerate(split_subtasks(task.query), start=1)
    ]


class DagStrategy:
    """Plan-driven DAG: ready-set serial/parallel, then synthesize."""

    name = "dag"

    def __init__(
        self,
        llm: CompletionClient,
        sandbox: SandboxClient | None = None,
        tools: ToolRegistry | None = None,
    ):
        self.llm = llm
        self.sandbox = sandbox
        self.tools = tools
        self._graph = self._build_graph()

    async def run(self, state: TaskState, emit: EmitFn) -> LLMResponse:
        graph_state: dict[str, Any] = {
            "task": state,
            "emit": emit,
            "subtasks": planned_subtasks(state),
            "results": {},
            "response": None,
        }
        if self._graph is not None:
            graph_state = await self._graph.ainvoke(graph_state)
        else:
            for node in (self.start_dag, self.execute_subtasks, self.finalize_dag):
                graph_state = await node(graph_state)
        return graph_state["response"]

    async def start_dag(self, state: dict[str, Any]) -> dict[str, Any]:
        task: TaskState = state["task"]
        emit: EmitFn = state["emit"]
        await emit(
            ShannonEvent(
                workflow_id=task.workflow_id,
                type="WORKFLOW_STARTED",
                agent_id="dag",
                message="DAG workflow started",
                payload={"subtasks": len(state["subtasks"])},
            )
        )
        await emit(
            ShannonEvent(
                workflow_id=task.workflow_id,
                type="DELEGATION",
                agent_id="orchestrator",
                message="Routing to DAG workflow",
            )
        )
        return state

    async def execute_subtasks(self, state: dict[str, Any]) -> dict[str, Any]:
        task: TaskState = state["task"]
        remaining = list(state["subtasks"])
        done: dict[str, str] = {}
        safety = 0
        while remaining and safety < 16:
            safety += 1
            ready = [item for item in remaining if all(dep in done for dep in item.get("dependencies") or [])]
            if not ready:
                ready = remaining[:1]
            batch = await self._run_ready_batch(task, state["emit"], ready, done)
            for item, text in zip(ready, batch):
                done[item["id"]] = text
            remaining = [item for item in remaining if item["id"] not in done]
        state["results"] = done
        return state

    async def _run_ready_batch(
        self,
        task: TaskState,
        emit: EmitFn,
        ready: list[dict[str, Any]],
        done: dict[str, str],
    ) -> list[str]:
        if len(ready) <= 1:
            return [await self._run_one(task, emit, ready[0], done)]
        return list(await asyncio.gather(*(self._run_one(task, emit, item, done) for item in ready)))

    async def _run_one(
        self,
        task: TaskState,
        emit: EmitFn,
        item: dict[str, Any],
        done: dict[str, str],
    ) -> str:
        raise_if_cancelled(task)
        raise_if_over_budget(task)
        agent_id = f"dag-agent-{item['id']}"
        await emit(
            ShannonEvent(
                workflow_id=task.workflow_id,
                type="AGENT_STARTED",
                agent_id=agent_id,
                message=item["description"],
            )
        )
        upstream = []
        for dep in item.get("dependencies") or []:
            if dep in done:
                upstream.append(f"{dep}: {done[dep]}")
        observations = await self._run_suggested_tools(task, emit, item)
        from puerflow_worker.strategies.memory import memory_messages

        messages = [
            {"role": "system", "content": "You are a PuerFlow DAG worker. Use tool results, then write only this subtask's conclusion."},
        ]
        messages.extend(memory_messages(task))
        if upstream:
            messages.append({"role": "system", "content": "Upstream results:\n" + "\n".join(upstream)})
        if observations:
            messages.append({"role": "system", "content": "Tool results:\n" + "\n".join(observations)})
        messages.append({"role": "user", "content": item["description"]})
        response = await complete_turn(self.llm, self.tools, task, emit, messages)
        raise_if_cancelled(task)
        await emit(
            ShannonEvent(
                workflow_id=task.workflow_id,
                type="AGENT_COMPLETED",
                agent_id=agent_id,
                message=response.content[:500],
            )
        )
        return response.content

    async def _run_suggested_tools(self, task: TaskState, emit: EmitFn, item: dict[str, Any]) -> list[str]:
        if self.tools is None:
            return []
        notes = []
        params = item.get("tool_parameters") or {}
        for name in item.get("suggested_tools") or []:
            result = await self.tools.execute(name, params if isinstance(params, dict) else {}, task=task, emit=emit)
            notes.append(f"{name}: {result.text or result.error or result.output}")
        return notes

    async def finalize_dag(self, state: dict[str, Any]) -> dict[str, Any]:
        task: TaskState = state["task"]
        emit: EmitFn = state["emit"]
        joined = "\n".join(f"- {key}: {value}" for key, value in (state.get("results") or {}).items())
        raise_if_cancelled(task)
        raise_if_over_budget(task)
        sandbox_note = ""
        if self.tools is None:
            sandbox_note = await maybe_run_sandbox(task, emit, self.sandbox)
        findings = joined
        if sandbox_note:
            findings = f"{joined}\nSandbox:\n{sandbox_note}"
        response = await complete_turn(
            self.llm,
            self.tools,
            task,
            emit,
            [
                {"role": "system", "content": "Synthesize DAG worker answers into one response."},
                {"role": "user", "content": f"Query: {task.query}\nFindings:\n{findings}"},
            ],
        )
        raise_if_cancelled(task)
        state["response"] = response
        await emit(
            ShannonEvent(
                workflow_id=task.workflow_id,
                type="LLM_OUTPUT",
                agent_id="final_output",
                message=response.content,
                payload={"text": response.content, "usage": response.usage.as_dict()},
            )
        )
        await emit(
            ShannonEvent(
                workflow_id=task.workflow_id,
                type="WORKFLOW_COMPLETED",
                agent_id="dag",
                message="DAG workflow completed",
            )
        )
        return state

    def _build_graph(self):
        if StateGraph is None:
            return None
        graph = StateGraph(dict)
        graph.add_node("start_dag", self.start_dag)
        graph.add_node("execute_subtasks", self.execute_subtasks)
        graph.add_node("finalize_dag", self.finalize_dag)
        graph.set_entry_point("start_dag")
        graph.add_edge("start_dag", "execute_subtasks")
        graph.add_edge("execute_subtasks", "finalize_dag")
        graph.add_edge("finalize_dag", END)
        return graph.compile()
