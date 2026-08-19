from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_GRPC_GEN = Path(__file__).resolve().parent / "grpc_gen"
if str(_GRPC_GEN) not in sys.path:
    sys.path.insert(0, str(_GRPC_GEN))

from google.protobuf.json_format import MessageToDict

from common import common_pb2
from strategy import strategy_pb2, strategy_pb2_grpc

from puerflow_worker.budget import BudgetExceeded
from puerflow_worker.runtime import TaskRegistry, TaskState
from puerflow_worker.settings import WorkerSettings

_KIND_NAMES = {
    strategy_pb2.STRATEGY_KIND_UNSPECIFIED: "sample",
    strategy_pb2.STRATEGY_KIND_SAMPLE: "sample",
    strategy_pb2.STRATEGY_KIND_SIMPLE: "sample",
    strategy_pb2.STRATEGY_KIND_DAG: "dag",
    strategy_pb2.STRATEGY_KIND_RESEARCH: "research",
    strategy_pb2.STRATEGY_KIND_SWARM: "swarm",
}

_STATUS = {
    "queued": strategy_pb2.STRATEGY_TASK_STATUS_QUEUED,
    "running": strategy_pb2.STRATEGY_TASK_STATUS_RUNNING,
    "waiting_approval": strategy_pb2.STRATEGY_TASK_STATUS_WAITING_APPROVAL,
    "completed": strategy_pb2.STRATEGY_TASK_STATUS_COMPLETED,
    "failed": strategy_pb2.STRATEGY_TASK_STATUS_FAILED,
    "cancelled": strategy_pb2.STRATEGY_TASK_STATUS_CANCELLED,
    "timeout": strategy_pb2.STRATEGY_TASK_STATUS_TIMEOUT,
}

_NAME_TO_KIND = {
    "sample": strategy_pb2.STRATEGY_KIND_SAMPLE,
    "dag": strategy_pb2.STRATEGY_KIND_DAG,
    "research": strategy_pb2.STRATEGY_KIND_RESEARCH,
    "swarm": strategy_pb2.STRATEGY_KIND_SWARM,
}

_FAILOVER_ERRORS = {
    strategy_pb2.STRATEGY_ERROR_STRATEGY_FAILED,
    strategy_pb2.STRATEGY_ERROR_TIMEOUT,
    strategy_pb2.STRATEGY_ERROR_UNAVAILABLE,
    strategy_pb2.STRATEGY_ERROR_FAILOVER,
}

_LIGHT_KINDS = {
    strategy_pb2.STRATEGY_KIND_SAMPLE,
    strategy_pb2.STRATEGY_KIND_SIMPLE,
    strategy_pb2.STRATEGY_KIND_UNSPECIFIED,
}


def build_failover_hint(last_error, failed_strategy):
    """Suggest Sample when a heavy strategy failed; never loop Sample onto itself."""
    light = failed_strategy in _LIGHT_KINDS
    eligible = last_error in _FAILOVER_ERRORS
    should = bool(eligible and not light)
    if should:
        reason = "fallback to sample"
    elif light and eligible:
        reason = "already on sample"
    elif last_error == strategy_pb2.STRATEGY_ERROR_BUDGET_EXCEEDED:
        reason = "budget exceeded is hard stop"
    elif last_error == strategy_pb2.STRATEGY_ERROR_CANCELLED:
        reason = "cancelled is not failover"
    else:
        reason = "no failover"
    return strategy_pb2.FailoverHint(
        should_failover=should,
        suggested_strategy=strategy_pb2.STRATEGY_KIND_SAMPLE if should else strategy_pb2.STRATEGY_KIND_UNSPECIFIED,
        reason=reason,
        retryable=should,
    )


def _struct_dict(value) -> dict:
    if value is None:
        return {}
    try:
        return MessageToDict(value)
    except Exception:  # noqa: BLE001
        return {}


class StrategyWorkerServicer(strategy_pb2_grpc.StrategyWorkerServicer):
    def __init__(
        self,
        registry: TaskRegistry,
        settings: WorkerSettings,
        strategies: dict,
    ):
        self.registry = registry
        self.settings = settings
        self.strategies = strategies

    async def Health(self, request, context):
        return strategy_pb2.HealthResponse(
            healthy=True,
            version=self.settings.version,
            message=self.settings.service_name,
        )

    async def Ready(self, request, context):
        missing = []
        if not self.registry.publisher.using_redis:
            missing.append("redis")
        return strategy_pb2.ReadyResponse(
            ready=True,
            missing_dependencies=missing,
            message="ready" if not missing else "degraded: redis optional",
        )

    async def RunStrategy(self, request, context):
        workflow_id = request.workflow_id or request.metadata.task_id
        task_id = request.metadata.task_id or workflow_id
        strategy = _KIND_NAMES.get(request.strategy, "sample")
        session = {
            "session_id": request.session.session_id,
            "user_id": request.session.user_id,
            "history": [
                {"role": item.role, "content": item.content} for item in request.session.history
            ],
            "qdrant_hits": [
                {"id": hit.id, "content": hit.content, "score": hit.score}
                for hit in request.session.qdrant_hits
            ],
        }
        state = TaskState(
            workflow_id=workflow_id,
            task_id=task_id,
            strategy=strategy,
            query=request.query,
            status="running",
            token_budget=request.budget.token_budget,
            session=session,
            context=_struct_dict(request.context),
            tools=list(request.available_tools),
            require_approval=bool(request.require_approval),
        )
        await self.registry.create(state)

        runner = self.strategies.get(strategy)
        if runner is None:
            state.status = "failed"
            state.error_code = strategy_pb2.STRATEGY_ERROR_NOT_FOUND
            state.error_message = f"unknown strategy {strategy}"
            return self._response(state)

        watch = asyncio.create_task(self._watch_grpc_cancel(context, state))
        try:
            if state.require_approval:
                approved = await self._wait_approval(state)
                if not approved:
                    return self._response(state)
                state.allow_dangerous_tools = True
            return await self._run_graph(state, runner)
        finally:
            watch.cancel()

    async def _wait_approval(self, state: TaskState) -> bool:
        state.status = "waiting_approval"
        await self.registry.emit(
            state.workflow_id,
            "WORKFLOW_PAUSED",
            "waiting for approval",
            agent_id="langgraph-worker",
        )
        try:
            await asyncio.wait_for(
                state.approval_event.wait(),
                timeout=self.settings.approval_timeout_seconds,
            )
        except asyncio.TimeoutError:
            state.status = "timeout"
            state.error_code = strategy_pb2.STRATEGY_ERROR_TIMEOUT
            state.error_message = "approval timed out"
            return False
        if not (state.approval or {}).get("approved", False):
            state.status = "cancelled"
            state.error_code = strategy_pb2.STRATEGY_ERROR_CANCELLED
            state.error_message = (state.approval or {}).get("comment") or "rejected"
            return False
        state.status = "running"
        return True

    async def _watch_grpc_cancel(self, context, state: TaskState) -> None:
        if context is None:
            return
        try:
            while True:
                cancelled = getattr(context, "cancelled", None)
                if callable(cancelled) and cancelled():
                    state.cancel_event.set()
                    return
                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            return

    async def _run_graph(self, state: TaskState, strategy):
        try:
            response = await strategy.run(state, self.registry.publisher.publish)
        except InterruptedError:
            state.status = "cancelled"
            state.error_code = strategy_pb2.STRATEGY_ERROR_CANCELLED
            state.error_message = "cancelled"
            return self._response(state)
        except BudgetExceeded as exc:
            state.status = "failed"
            state.error_code = strategy_pb2.STRATEGY_ERROR_BUDGET_EXCEEDED
            state.error_message = str(exc)
            state.tokens_used = exc.used
            await self.registry.emit(state.workflow_id, "WORKFLOW_FAILED", state.error_message)
            return self._response(state)
        except Exception as exc:  # noqa: BLE001
            state.status = "failed"
            state.error_code = strategy_pb2.STRATEGY_ERROR_STRATEGY_FAILED
            state.error_message = str(exc)
            await self.registry.emit(state.workflow_id, "WORKFLOW_FAILED", state.error_message)
            return self._response(state)

        if state.cancel_event.is_set():
            state.status = "cancelled"
            state.error_code = strategy_pb2.STRATEGY_ERROR_CANCELLED
            state.error_message = state.error_message or "cancelled"
            return self._response(state)

        state.result = response.content
        state.status = "completed"
        state.progress = 1.0
        state.current_step = strategy.name
        state.tokens_used = max(state.tokens_used, response.usage.total_tokens)
        state.error_code = strategy_pb2.STRATEGY_ERROR_OK
        return self._response(state)

    async def Cancel(self, request, context):
        state = await self.registry.request_cancel(
            request.workflow_id, request.task_id, request.reason
        )
        if state is None:
            return strategy_pb2.CancelResponse(accepted=False, message="task not found")
        return strategy_pb2.CancelResponse(
            accepted=True,
            task_status=_STATUS.get(state.status, strategy_pb2.STRATEGY_TASK_STATUS_CANCELLED),
            message="cancel accepted",
        )

    async def GetStatus(self, request, context):
        state = await self.registry.get(request.workflow_id, request.task_id)
        if state is None:
            return strategy_pb2.GetStatusResponse(
                workflow_id=request.workflow_id,
                task_id=request.task_id,
                task_status=strategy_pb2.STRATEGY_TASK_STATUS_UNSPECIFIED,
                error_message="task not found",
                error_code=strategy_pb2.STRATEGY_ERROR_NOT_FOUND,
            )
        return strategy_pb2.GetStatusResponse(
            workflow_id=state.workflow_id,
            task_id=state.task_id,
            task_status=_STATUS.get(state.status, strategy_pb2.STRATEGY_TASK_STATUS_UNSPECIFIED),
            progress=state.progress,
            result=state.result,
            error_message=state.error_message,
            error_code=state.error_code,
            budget=strategy_pb2.Budget(
                token_budget=state.token_budget, tokens_used=state.tokens_used
            ),
            failover=build_failover_hint(
                state.error_code, _NAME_TO_KIND.get(state.strategy, strategy_pb2.STRATEGY_KIND_SAMPLE)
            ),
            current_step=state.current_step,
        )

    async def ApproveDecision(self, request, context):
        state = await self.registry.get(request.workflow_id, request.task_id)
        if state is None:
            return strategy_pb2.ApproveDecisionResponse(applied=False, message="task not found")
        state.approval = {
            "approval_id": request.approval_id,
            "approved": request.approved,
            "comment": request.comment,
            "reviewer": request.reviewer,
        }
        state.approval_event.set()
        if request.approved and state.status == "waiting_approval":
            state.status = "running"
        elif not request.approved:
            state.status = "cancelled"
            state.error_code = strategy_pb2.STRATEGY_ERROR_CANCELLED
            state.cancel_event.set()
        return strategy_pb2.ApproveDecisionResponse(
            applied=True,
            task_status=_STATUS.get(state.status, strategy_pb2.STRATEGY_TASK_STATUS_UNSPECIFIED),
            message="decision recorded",
        )

    async def BudgetReport(self, request, context):
        state = await self.registry.get(request.workflow_id, request.task_id)
        budget = strategy_pb2.Budget()
        if state is not None:
            budget.token_budget = state.token_budget
            budget.tokens_used = state.tokens_used
            budget.exceeded = bool(state.token_budget and state.tokens_used >= state.token_budget)
            budget.near_limit = bool(
                state.token_budget and state.tokens_used >= int(state.token_budget * 0.8)
            )
        return strategy_pb2.BudgetReportResponse(
            task_budget=budget,
            hard_stop=budget.exceeded,
            degrade=budget.near_limit and not budget.exceeded,
        )

    async def InjectSessionContext(self, request, context):
        state = await self.registry.get(request.workflow_id, request.task_id)
        if state is None:
            state = TaskState(
                workflow_id=request.workflow_id,
                task_id=request.task_id or request.workflow_id,
                strategy="sample",
                query="",
            )
            await self.registry.create(state)
        state.session = {
            "session_id": request.session.session_id,
            "user_id": request.session.user_id,
            "history": [
                {"role": item.role, "content": item.content} for item in request.session.history
            ],
            "history_len": len(request.session.history),
            "qdrant_hits": [
                {"id": hit.id, "content": hit.content, "score": hit.score}
                for hit in request.session.qdrant_hits
            ],
        }
        return strategy_pb2.InjectSessionContextResponse(
            applied=True,
            history_messages=len(request.session.history),
            qdrant_hits=len(request.session.qdrant_hits),
        )

    async def GetFailoverHint(self, request, context):
        return strategy_pb2.GetFailoverHintResponse(
            hint=build_failover_hint(request.last_error, request.failed_strategy)
        )

    def _response(self, state: TaskState) -> strategy_pb2.RunStrategyResponse:
        ok = state.status == "completed"
        budget = strategy_pb2.Budget(
            token_budget=state.token_budget,
            tokens_used=state.tokens_used,
            exceeded=bool(state.token_budget and state.tokens_used >= state.token_budget),
        )
        error_code = strategy_pb2.STRATEGY_ERROR_OK if ok else state.error_code
        failed_kind = _NAME_TO_KIND.get(state.strategy, strategy_pb2.STRATEGY_KIND_SAMPLE)
        return strategy_pb2.RunStrategyResponse(
            workflow_id=state.workflow_id,
            task_id=state.task_id,
            status=common_pb2.STATUS_CODE_OK if ok else common_pb2.STATUS_CODE_ERROR,
            error_code=error_code,
            task_status=_STATUS.get(state.status, strategy_pb2.STRATEGY_TASK_STATUS_UNSPECIFIED),
            result=state.result,
            error_message=state.error_message,
            budget=budget,
            failover=None if ok else build_failover_hint(error_code, failed_kind),
        )
