from __future__ import annotations

from typing import Any, Awaitable, Callable

from puerflow_worker.events import ShannonEvent
from puerflow_worker.llm import CompletionClient, LLMResponse
from puerflow_worker.runtime import TaskState

try:
    from langgraph.graph import END, StateGraph
except Exception:  # noqa: BLE001
    END = None
    StateGraph = None

EmitFn = Callable[[ShannonEvent], Awaitable[None]]


class SampleStrategy:
    """AstraFlow Sample graph: prepare → memory → prompt → LLM → persist."""

    name = "sample"

    def __init__(self, llm: CompletionClient):
        self.llm = llm
        self._graph = self._build_graph()

    async def run(self, state: TaskState, emit: EmitFn) -> LLMResponse:
        graph_state: dict[str, Any] = {
            "task": state,
            "emit": emit,
            "messages": [],
            "history": [],
            "response": None,
        }
        if self._graph is not None:
            graph_state = await self._graph.ainvoke(graph_state)
        else:
            for node in (
                self.prepare_context,
                self.load_memory,
                self.build_messages,
                self.call_llm,
                self.persist_result,
            ):
                graph_state = await node(graph_state)
        return graph_state["response"]

    async def prepare_context(self, state: dict[str, Any]) -> dict[str, Any]:
        task: TaskState = state["task"]
        emit: EmitFn = state["emit"]
        agent_id = f"{task.strategy}-agent"
        await emit(
            ShannonEvent(
                workflow_id=task.workflow_id,
                type="WORKFLOW_STARTED",
                agent_id="orchestrator",
                message="Workflow started",
            )
        )
        await emit(
            ShannonEvent(
                workflow_id=task.workflow_id,
                type="DELEGATION",
                agent_id="orchestrator",
                message=f"Routing to {task.strategy}",
            )
        )
        await emit(
            ShannonEvent(
                workflow_id=task.workflow_id,
                type="AGENT_STARTED",
                agent_id=agent_id,
                message="Agent started",
            )
        )
        return state

    async def load_memory(self, state: dict[str, Any]) -> dict[str, Any]:
        task: TaskState = state["task"]
        history = []
        session = task.session or {}
        for item in session.get("history") or []:
            history.append({"role": item.get("role", "user"), "content": item.get("content", "")})
        state["history"] = history[-8:]
        return state

    async def build_messages(self, state: dict[str, Any]) -> dict[str, Any]:
        task: TaskState = state["task"]
        emit: EmitFn = state["emit"]
        messages = [
            {
                "role": "system",
                "content": "You are PuerFlow, a concise workflow agent using the Sample strategy.",
            }
        ]
        messages.extend(state.get("history") or [])
        messages.append({"role": "user", "content": task.query})
        state["messages"] = messages
        await emit(
            ShannonEvent(
                workflow_id=task.workflow_id,
                type="LLM_PROMPT",
                agent_id=f"{task.strategy}-agent",
                message="Prompt prepared",
            )
        )
        return state

    async def call_llm(self, state: dict[str, Any]) -> dict[str, Any]:
        task: TaskState = state["task"]
        if task.cancel_event.is_set():
            raise InterruptedError("cancelled")
        state["response"] = await self.llm.generate(state["messages"])
        return state

    async def persist_result(self, state: dict[str, Any]) -> dict[str, Any]:
        task: TaskState = state["task"]
        emit: EmitFn = state["emit"]
        response: LLMResponse = state["response"]
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
                type="AGENT_COMPLETED",
                agent_id=f"{task.strategy}-agent",
                message="Agent completed",
            )
        )
        await emit(
            ShannonEvent(
                workflow_id=task.workflow_id,
                type="WORKFLOW_COMPLETED",
                agent_id="orchestrator",
                message="Workflow completed",
            )
        )
        return state

    def _build_graph(self):
        if StateGraph is None:
            return None
        graph = StateGraph(dict)
        graph.add_node("prepare_context", self.prepare_context)
        graph.add_node("load_memory", self.load_memory)
        graph.add_node("build_messages", self.build_messages)
        graph.add_node("call_llm", self.call_llm)
        graph.add_node("persist_result", self.persist_result)
        graph.set_entry_point("prepare_context")
        graph.add_edge("prepare_context", "load_memory")
        graph.add_edge("load_memory", "build_messages")
        graph.add_edge("build_messages", "call_llm")
        graph.add_edge("call_llm", "persist_result")
        graph.add_edge("persist_result", END)
        return graph.compile()
