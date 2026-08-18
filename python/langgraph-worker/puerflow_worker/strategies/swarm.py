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

_ROLES = ("analyst", "critic")


class SwarmStrategy:
    """AstraFlow-style swarm: lead recruits roles, workers answer, lead synthesizes."""

    name = "swarm"

    def __init__(self, llm: CompletionClient):
        self.llm = llm
        self._graph = self._build_graph()

    async def run(self, state: TaskState, emit: EmitFn) -> LLMResponse:
        graph_state: dict[str, Any] = {"task": state, "emit": emit, "notes": [], "response": None}
        if self._graph is not None:
            graph_state = await self._graph.ainvoke(graph_state)
        else:
            for node in (self.recruit, self.workers, self.lead_synthesize):
                graph_state = await node(graph_state)
        return graph_state["response"]

    async def recruit(self, state: dict[str, Any]) -> dict[str, Any]:
        task: TaskState = state["task"]
        emit: EmitFn = state["emit"]
        await emit(
            ShannonEvent(
                workflow_id=task.workflow_id,
                type="WORKFLOW_STARTED",
                agent_id="swarm-lead",
                message="Swarm workflow started",
            )
        )
        await emit(
            ShannonEvent(
                workflow_id=task.workflow_id,
                type="TEAM_RECRUITED",
                agent_id="swarm-lead",
                message="Recruited analyst and critic",
                payload={"roles": list(_ROLES)},
            )
        )
        return state

    async def workers(self, state: dict[str, Any]) -> dict[str, Any]:
        task: TaskState = state["task"]
        emit: EmitFn = state["emit"]
        notes = []
        for role in _ROLES:
            if task.cancel_event.is_set():
                raise InterruptedError("cancelled")
            await emit(
                ShannonEvent(
                    workflow_id=task.workflow_id,
                    type="AGENT_STARTED",
                    agent_id=f"swarm-{role}",
                    message=f"{role} started",
                )
            )
            response = await self.llm.generate(
                [
                    {"role": "system", "content": f"You are the swarm {role}. Give a focused take."},
                    {"role": "user", "content": task.query},
                ]
            )
            notes.append(f"{role}: {response.content}")
            await emit(
                ShannonEvent(
                    workflow_id=task.workflow_id,
                    type="AGENT_COMPLETED",
                    agent_id=f"swarm-{role}",
                    message=response.content[:500],
                )
            )
        state["notes"] = notes
        return state

    async def lead_synthesize(self, state: dict[str, Any]) -> dict[str, Any]:
        task: TaskState = state["task"]
        emit: EmitFn = state["emit"]
        joined = "\n".join(state["notes"])
        response = await self.llm.generate(
            [
                {"role": "system", "content": "You are the swarm lead. Merge teammate views into one answer."},
                {"role": "user", "content": f"Query: {task.query}\nTeammates:\n{joined}"},
            ]
        )
        state["response"] = response
        await emit(
            ShannonEvent(
                workflow_id=task.workflow_id,
                type="LEAD_DECISION",
                agent_id="swarm-lead",
                message="Lead synthesized teammate answers",
            )
        )
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
                agent_id="swarm-lead",
                message="Swarm workflow completed",
            )
        )
        return state

    def _build_graph(self):
        if StateGraph is None:
            return None
        graph = StateGraph(dict)
        graph.add_node("recruit", self.recruit)
        graph.add_node("workers", self.workers)
        graph.add_node("lead_synthesize", self.lead_synthesize)
        graph.set_entry_point("recruit")
        graph.add_edge("recruit", "workers")
        graph.add_edge("workers", "lead_synthesize")
        graph.add_edge("lead_synthesize", END)
        return graph.compile()
