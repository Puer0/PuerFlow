from __future__ import annotations

import json
import re
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
_ROLES = ("researcher", "analyst", "writer", "critic")
_JSON_BLOCK = re.compile(r"\[.*\]", re.S)
_MAX_READY = 3
_WORKER_ROUNDS = 3


def parse_board(raw: str, query: str) -> list[dict[str, Any]]:
    text = raw or ""
    match = _JSON_BLOCK.search(text)
    payload = []
    if match:
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            payload = []
    if not isinstance(payload, list) or not payload:
        return [
            {"id": "t1", "title": query, "owner": "analyst", "dependencies": [], "done": False, "result": ""},
            {"id": "t2", "title": f"Review: {query}", "owner": "critic", "dependencies": ["t1"], "done": False, "result": ""},
        ]
    board = []
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            continue
        owner = str(item.get("owner") or item.get("role") or "analyst").lower()
        if owner not in _ROLES:
            owner = "analyst"
        board.append(
            {
                "id": str(item.get("id") or f"t{index}"),
                "title": str(item.get("title") or item.get("task") or query),
                "owner": owner,
                "dependencies": [str(dep) for dep in (item.get("dependencies") or [])],
                "done": False,
                "result": "",
            }
        )
    return board or [
        {"id": "t1", "title": query, "owner": "analyst", "dependencies": [], "done": False, "result": ""},
    ]


def ready_tasks(board: list[dict[str, Any]]) -> list[dict[str, Any]]:
    done_ids = {item["id"] for item in board if item.get("done")}
    ready = []
    seen_owners: set[str] = set()
    for item in board:
        if item.get("done"):
            continue
        if any(dep not in done_ids for dep in item.get("dependencies") or []):
            continue
        if item["owner"] in seen_owners:
            continue
        seen_owners.add(item["owner"])
        ready.append(item)
        if len(ready) >= _MAX_READY:
            break
    return ready


class SwarmStrategy:
    """Lead builds a kanban, ready owners run bounded loops, lead synthesizes."""

    name = "swarm"

    def __init__(self, llm: CompletionClient, tools: ToolRegistry | None = None):
        self.llm = llm
        self.tools = tools
        self._graph = self._build_graph()

    async def run(self, state: TaskState, emit: EmitFn) -> LLMResponse:
        graph_state: dict[str, Any] = {"task": state, "emit": emit, "board": [], "notes": [], "response": None}
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
        raise_if_cancelled(task)
        raise_if_over_budget(task)
        from puerflow_worker.strategies.memory import memory_messages

        messages = [
            {
                "role": "system",
                "content": (
                    "You are the swarm lead. Return a JSON list of tasks. "
                    'Each item: {"id","title","owner","dependencies"}. '
                    f"Owners must be one of: {', '.join(_ROLES)}."
                ),
            },
        ]
        messages.extend(memory_messages(task))
        messages.append({"role": "user", "content": task.query})
        plan = await complete_turn(self.llm, None, task, emit, messages)
        board = parse_board(plan.content, task.query)
        state["board"] = board
        await emit(
            ShannonEvent(
                workflow_id=task.workflow_id,
                type="TEAM_RECRUITED",
                agent_id="swarm-lead",
                message="Lead published the task board",
                payload={"roles": sorted({item["owner"] for item in board}), "tasks": len(board)},
            )
        )
        return state

    async def workers(self, state: dict[str, Any]) -> dict[str, Any]:
        task: TaskState = state["task"]
        emit: EmitFn = state["emit"]
        board: list[dict[str, Any]] = state["board"]
        notes = []
        safety = 0
        while any(not item.get("done") for item in board) and safety < 8:
            safety += 1
            ready = ready_tasks(board)
            if not ready:
                for item in board:
                    if not item.get("done"):
                        ready = [item]
                        break
            batch = []
            for item in ready:
                batch.append(self._run_worker(task, emit, item, board))
            results = await _gather(batch)
            for item, text in zip(ready, results):
                item["done"] = True
                item["result"] = text
                notes.append(f"{item['owner']} / {item['id']}: {text}")
        state["notes"] = notes
        return state

    async def _run_worker(
        self,
        task: TaskState,
        emit: EmitFn,
        item: dict[str, Any],
        board: list[dict[str, Any]],
    ) -> str:
        raise_if_cancelled(task)
        raise_if_over_budget(task)
        role = item["owner"]
        await emit(
            ShannonEvent(
                workflow_id=task.workflow_id,
                type="AGENT_STARTED",
                agent_id=f"swarm-{role}",
                message=f"{role} started {item['id']}",
            )
        )
        prior = "\n".join(f"{row['id']}: {row.get('result')}" for row in board if row.get("done") and row.get("result"))
        messages = [
            {
                "role": "system",
                "content": (
                    f"You are the swarm {role}. Complete only this kanban task. "
                    "You may use tools. Keep findings usable by teammates."
                ),
            },
        ]
        if prior:
            messages.append({"role": "system", "content": f"Board results so far:\n{prior}"})
        messages.append({"role": "user", "content": f"{item['title']}\nOriginal query: {task.query}"})
        last = ""
        for _ in range(_WORKER_ROUNDS):
            response = await complete_turn(self.llm, self.tools, task, emit, messages, max_rounds=_WORKER_ROUNDS)
            last = response.content
            if last:
                break
        await emit(
            ShannonEvent(
                workflow_id=task.workflow_id,
                type="AGENT_COMPLETED",
                agent_id=f"swarm-{role}",
                message=(last or "")[:500],
            )
        )
        return last

    async def lead_synthesize(self, state: dict[str, Any]) -> dict[str, Any]:
        task: TaskState = state["task"]
        emit: EmitFn = state["emit"]
        raise_if_cancelled(task)
        raise_if_over_budget(task)
        joined = "\n".join(state["notes"])
        response = await complete_turn(
            self.llm,
            self.tools,
            task,
            emit,
            [
                {"role": "system", "content": "You are the swarm lead. Merge teammate board results into one answer."},
                {"role": "user", "content": f"Query: {task.query}\nBoard:\n{joined}"},
            ],
        )
        raise_if_cancelled(task)
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


async def _gather(jobs: list[Awaitable[str]]) -> list[str]:
    import asyncio

    if len(jobs) <= 1:
        return [await jobs[0]] if jobs else []
    return list(await asyncio.gather(*jobs))
