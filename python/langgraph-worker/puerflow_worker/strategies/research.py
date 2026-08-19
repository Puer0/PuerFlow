from __future__ import annotations

from typing import Any, Awaitable, Callable

from puerflow_worker.events import ShannonEvent
from puerflow_worker.llm import CompletionClient, LLMResponse
from puerflow_worker.runtime import TaskState
from puerflow_worker.budget import raise_if_cancelled, raise_if_over_budget
from puerflow_worker.tools import complete_turn
from puerflow_worker.tools.registry import ToolRegistry

try:
    from langgraph.graph import END, StateGraph
except Exception:  # noqa: BLE001
    END = None
    StateGraph = None

EmitFn = Callable[[ShannonEvent], Awaitable[None]]


class ResearchStrategy:
    """AstraFlow-style research: plan → investigate → synthesize."""

    name = "research"

    def __init__(self, llm: CompletionClient, tools: ToolRegistry | None = None):
        self.llm = llm
        self.tools = tools
        self._graph = self._build_graph()

    async def run(self, state: TaskState, emit: EmitFn) -> LLMResponse:
        graph_state: dict[str, Any] = {"task": state, "emit": emit, "notes": "", "response": None}
        if self._graph is not None:
            graph_state = await self._graph.ainvoke(graph_state)
        else:
            for node in (self.start, self.investigate, self.synthesize):
                graph_state = await node(graph_state)
        return graph_state["response"]

    async def start(self, state: dict[str, Any]) -> dict[str, Any]:
        task: TaskState = state["task"]
        emit: EmitFn = state["emit"]
        await emit(
            ShannonEvent(
                workflow_id=task.workflow_id,
                type="WORKFLOW_STARTED",
                agent_id="research",
                message="Research workflow started",
            )
        )
        await emit(
            ShannonEvent(
                workflow_id=task.workflow_id,
                type="RESEARCH_PLAN_READY",
                agent_id="research",
                message="Research plan ready",
            )
        )
        return state

    async def investigate(self, state: dict[str, Any]) -> dict[str, Any]:
        task: TaskState = state["task"]
        raise_if_cancelled(task)
        raise_if_over_budget(task)
        response = await complete_turn(
            self.llm,
            self.tools,
            task,
            state["emit"],
            [
                {"role": "system", "content": "You are a PuerFlow research agent. Outline key facts."},
                {"role": "user", "content": task.query},
            ],
        )
        raise_if_cancelled(task)
        state["notes"] = response.content
        emit: EmitFn = state["emit"]
        await emit(
            ShannonEvent(
                workflow_id=task.workflow_id,
                type="AGENT_COMPLETED",
                agent_id="research-agent",
                message=response.content[:500],
            )
        )
        return state

    async def synthesize(self, state: dict[str, Any]) -> dict[str, Any]:
        task: TaskState = state["task"]
        emit: EmitFn = state["emit"]
        raise_if_cancelled(task)
        raise_if_over_budget(task)
        response = await complete_turn(
            self.llm,
            self.tools,
            task,
            emit,
            [
                {"role": "system", "content": "Write a careful research answer with caveats."},
                {"role": "user", "content": f"Query: {task.query}\nNotes:\n{state['notes']}"},
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
                agent_id="research",
                message="Research workflow completed",
            )
        )
        return state

    def _build_graph(self):
        if StateGraph is None:
            return None
        graph = StateGraph(dict)
        graph.add_node("start", self.start)
        graph.add_node("investigate", self.investigate)
        graph.add_node("synthesize", self.synthesize)
        graph.set_entry_point("start")
        graph.add_edge("start", "investigate")
        graph.add_edge("investigate", "synthesize")
        graph.add_edge("synthesize", END)
        return graph.compile()
