from __future__ import annotations

from puerflow_worker.runtime import TaskState


class BudgetExceeded(Exception):
    def __init__(self, used: int, budget: int):
        super().__init__(f"budget exceeded: used={used} budget={budget}")
        self.used = used
        self.budget = budget


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
