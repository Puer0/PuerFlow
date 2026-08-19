from __future__ import annotations

import re
from typing import Any, Awaitable, Callable

from puerflow_worker.budget import raise_if_cancelled
from puerflow_worker.events import ShannonEvent
from puerflow_worker.runtime import TaskState
from puerflow_worker.sandbox import SandboxClient

EmitFn = Callable[[ShannonEvent], Awaitable[None]]

_FENCE = re.compile(r"```(?:python)?\n(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_python(query: str) -> str | None:
    match = _FENCE.search(query or "")
    if not match:
        return None
    code = match.group(1).strip()
    return code or None


async def maybe_run_sandbox(
    task: TaskState,
    emit: EmitFn,
    sandbox: SandboxClient | None,
) -> str:
    if sandbox is None:
        return ""
    code = extract_python(task.query)
    if not code:
        return ""
    raise_if_cancelled(task)
    agent_id = f"{task.strategy}-agent"
    await emit(
        ShannonEvent(
            workflow_id=task.workflow_id,
            type="TOOL_INVOKED",
            agent_id=agent_id,
            message="code_executor",
            payload={"tool": "code_executor"},
        )
    )
    session_id = (task.session or {}).get("session_id") or task.workflow_id
    user_id = (task.session or {}).get("user_id") or ""
    staging_path = f"staging/{task.workflow_id}.py"
    await sandbox.file_write(staging_path, code, session_id=session_id, user_id=user_id)
    result = await sandbox.execute_python(code, session_id=session_id, user_id=user_id)
    output = (result.stdout or result.error or "").strip()
    event_type = "TOOL_OBSERVATION" if result.success or result.skipped else "TOOL_ERROR"
    await emit(
        ShannonEvent(
            workflow_id=task.workflow_id,
            type=event_type,
            agent_id=agent_id,
            message=output[:2000] or ("skipped" if result.skipped else "failed"),
            payload={"skipped": result.skipped, "success": result.success},
        )
    )
    if result.success and output:
        await sandbox.file_write(
            f"workspace/{task.workflow_id}.out",
            output,
            session_id=session_id,
            user_id=user_id,
        )
    return output
