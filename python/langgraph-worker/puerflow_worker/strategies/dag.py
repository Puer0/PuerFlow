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


def split_subtasks(query: str) -> list[str]:
    raw = [part.strip() for part in query.replace("；", ";").replace("和", ";").split(";") if part.strip()]
    if len(raw) >= 2:
        return raw[:4]
    return [f"Analyze: {query}", f"Answer: {query}"]


class DagStrategy:
    """AstraFlow-style DAG: start → execute subtasks → synthesize."""

    name = "dag"

    def __init__(self, llm: CompletionClient):
        self.llm = llm
        self._graph = self._build_graph()

    async def run(self, state: TaskState, emit: EmitFn) -> LLMResponse:
        graph_state: dict[str, Any] = {
            "task": state,
            "emit": emit,
            "subtasks": split_subtasks(state.query),
            "results": [],
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
        emit: EmitFn = state["emit"]
        results: list[str] = []
        for index, subtask in enumerate(state["subtasks"], start=1):
            if task.cancel_event.is_set():
                raise InterruptedError("cancelled")
            agent_id = f"dag-agent-{index}"
            await emit(
                ShannonEvent(
                    workflow_id=task.workflow_id,
                    type="AGENT_STARTED",
                    agent_id=agent_id,
                    message=subtask,
                )
            )
            response = await self.llm.generate(
                [
                    {"role": "system", "content": "You are a PuerFlow DAG worker. Answer only this subtask."},
                    {"role": "user", "content": subtask},
                ]
            )
            results.append(response.content)
            await emit(
                ShannonEvent(
                    workflow_id=task.workflow_id,
                    type="AGENT_COMPLETED",
                    agent_id=agent_id,
                    message=response.content[:500],
                )
            )
        state["results"] = results
        return state

    async def finalize_dag(self, state: dict[str, Any]) -> dict[str, Any]:
        task: TaskState = state["task"]
        emit: EmitFn = state["emit"]
        joined = "\n".join(f"- {item}" for item in state["results"])
        response = await self.llm.generate(
            [
                {"role": "system", "content": "Synthesize DAG worker answers into one response."},
                {"role": "user", "content": f"Query: {task.query}\nFindings:\n{joined}"},
            ]
        )
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
