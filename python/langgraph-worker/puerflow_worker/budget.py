from __future__ import annotations

from puerflow_worker.runtime import TaskState

_TIER_ORDER = ("small", "medium", "large")


class BudgetExceeded(Exception):
    def __init__(self, used: int, budget: int):
        super().__init__(f"budget exceeded: used={used} budget={budget}")
        self.used = used
        self.budget = budget


def degrade_model_tier(tier: str, task: TaskState) -> str:
    current = (tier or "small").strip().lower()
    if current not in _TIER_ORDER:
        current = "small"
    if not task.token_budget:
        return current
    if task.tokens_used >= int(task.token_budget * 0.8):
        if current == "large":
            return "medium"
        return "small"
    return current


def raise_if_cancelled(task: TaskState) -> None:
    if task.cancel_event.is_set():
        raise InterruptedError("cancelled")


def raise_if_over_budget(task: TaskState) -> None:
    if task.token_budget and task.tokens_used >= task.token_budget:
        raise BudgetExceeded(task.tokens_used, task.token_budget)


def add_tokens(task: TaskState, used: int) -> None:
    if used:
        task.tokens_used += int(used)
    raise_if_over_budget(task)
