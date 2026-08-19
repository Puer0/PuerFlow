from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from puerflow_worker.events import ShannonEvent, ShannonEventPublisher


@dataclass
class TaskState:
    workflow_id: str
    task_id: str
    strategy: str
    query: str
    status: str = "queued"
    result: str = ""
    error_message: str = ""
    error_code: int = 1  # STRATEGY_ERROR_OK
    progress: float = 0.0
    current_step: str = ""
    tokens_used: int = 0
    token_budget: int = 0
    session: dict[str, Any] = field(default_factory=dict)
    approval: dict[str, Any] | None = None
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    approval_event: asyncio.Event = field(default_factory=asyncio.Event)
    context: dict[str, Any] = field(default_factory=dict)
    tools: list[str] = field(default_factory=list)
    require_approval: bool = False


class TaskRegistry:
    def __init__(self, publisher: ShannonEventPublisher):
        self.publisher = publisher
        self._tasks: dict[str, TaskState] = {}
        self._lock = asyncio.Lock()

    def _key(self, workflow_id: str, task_id: str = "") -> str:
        return workflow_id or task_id

    async def create(self, state: TaskState) -> TaskState:
        async with self._lock:
            self._tasks[self._key(state.workflow_id, state.task_id)] = state
        return state

    async def get(self, workflow_id: str, task_id: str = "") -> TaskState | None:
        async with self._lock:
            found = self._tasks.get(self._key(workflow_id, task_id))
            if found is not None:
                return found
            if task_id:
                return self._tasks.get(task_id)
            return None

    async def request_cancel(self, workflow_id: str, task_id: str, reason: str) -> TaskState | None:
        state = await self.get(workflow_id, task_id)
        if state is None:
            return None
        state.cancel_event.set()
        if state.status in {"queued", "running", "waiting_approval"}:
            state.status = "cancelled"
            state.error_message = reason or "cancelled"
            state.error_code = 4  # STRATEGY_ERROR_CANCELLED
        await self.publisher.publish(
            ShannonEvent(
                workflow_id=state.workflow_id,
                type="WORKFLOW_FAILED",
                agent_id="langgraph-worker",
                message=state.error_message or "cancelled",
            )
        )
        return state

    async def emit(self, workflow_id: str, event_type: str, message: str, agent_id: str = "langgraph-worker") -> None:
        await self.publisher.publish(
            ShannonEvent(workflow_id=workflow_id, type=event_type, agent_id=agent_id, message=message)
        )
