from __future__ import annotations

from typing import Any

from puerflow_worker.runtime import TaskState


def memory_messages(task: TaskState, limit: int = 8) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    session = task.session or {}
    for item in session.get("history") or []:
        history.append({"role": item.get("role", "user"), "content": item.get("content", "")})
    for hit in session.get("qdrant_hits") or []:
        content = hit.get("content") if isinstance(hit, dict) else str(hit)
        if content:
            history.append({"role": "system", "content": f"memory: {content}"})
    memory = (task.context or {}).get("agent_memory")
    if memory:
        history.append({"role": "system", "content": f"session memory: {memory}"})
    return history[-limit:]
