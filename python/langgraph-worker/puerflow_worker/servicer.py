from __future__ import annotations

import sys
from pathlib import Path

_GRPC_GEN = Path(__file__).resolve().parent / "grpc_gen"
if str(_GRPC_GEN) not in sys.path:
    sys.path.insert(0, str(_GRPC_GEN))

from common import common_pb2
from strategy import strategy_pb2, strategy_pb2_grpc

from puerflow_worker.llm import CompletionClient
from puerflow_worker.runtime import TaskRegistry, TaskState
from puerflow_worker.settings import WorkerSettings
from puerflow_worker.strategies.sample import SampleStrategy

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


class StrategyWorkerServicer(strategy_pb2_grpc.StrategyWorkerServicer):
    def __init__(self, registry: TaskRegistry, settings: WorkerSettings, sample: SampleStrategy):
        self.registry = registry
        self.settings = settings
        self.sample = sample

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
        state = TaskState(
            workflow_id=workflow_id,
            task_id=task_id,
            strategy=strategy,
            query=request.query,
            status="running",
            token_budget=request.budget.token_budget,
            session={"session_id": request.session.session_id} if request.session.session_id else {},
        )
        await self.registry.create(state)
        if request.session.history:
            state.session["history"] = [
                {"role": item.role, "content": item.content} for item in request.session.history
            ]

        if strategy == "sample":
            return await self._run_sample(state)

        await self.registry.emit(workflow_id, "WORKFLOW_STARTED", f"strategy={strategy}")
        if state.cancel_event.is_set():
            state.status = "cancelled"
            state.error_code = strategy_pb2.STRATEGY_ERROR_CANCELLED
            return self._response(state)

        # DAG / Research / Swarm are wired in later branches.
        state.result = f"[{strategy}] {request.query}".strip()
        state.status = "completed"
        state.progress = 1.0
        state.current_step = "stub"
        state.error_code = strategy_pb2.STRATEGY_ERROR_OK
        await self.registry.emit(
            workflow_id,
            "WORKFLOW_COMPLETED",
            "All done",
            agent_id=f"{strategy}-agent",
        )
        return self._response(state)

    async def _run_sample(self, state: TaskState):
        try:
            response = await self.sample.run(state, self.registry.publisher.publish)
        except InterruptedError:
            state.status = "cancelled"
            state.error_code = strategy_pb2.STRATEGY_ERROR_CANCELLED
            state.error_message = "cancelled"
            return self._response(state)
        except Exception as exc:  # noqa: BLE001
            state.status = "failed"
            state.error_code = strategy_pb2.STRATEGY_ERROR_STRATEGY_FAILED
            state.error_message = str(exc)
            await self.registry.emit(state.workflow_id, "WORKFLOW_FAILED", state.error_message)
            return self._response(state)

        state.result = response.content
        state.status = "completed"
        state.progress = 1.0
        state.current_step = "sample"
        state.tokens_used = response.usage.total_tokens
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
        if request.approved and state.status == "waiting_approval":
            state.status = "running"
        elif not request.approved:
            state.status = "cancelled"
            state.error_code = strategy_pb2.STRATEGY_ERROR_CANCELLED
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
            "history_len": len(request.session.history),
            "qdrant_hits": len(request.session.qdrant_hits),
        }
        return strategy_pb2.InjectSessionContextResponse(
            applied=True,
            history_messages=len(request.session.history),
            qdrant_hits=len(request.session.qdrant_hits),
        )

    async def GetFailoverHint(self, request, context):
        hint = strategy_pb2.FailoverHint(
            should_failover=request.last_error
            in (
                strategy_pb2.STRATEGY_ERROR_STRATEGY_FAILED,
                strategy_pb2.STRATEGY_ERROR_TIMEOUT,
                strategy_pb2.STRATEGY_ERROR_UNAVAILABLE,
            ),
            suggested_strategy=strategy_pb2.STRATEGY_KIND_SAMPLE,
            reason="fallback to sample",
            retryable=True,
        )
        return strategy_pb2.GetFailoverHintResponse(hint=hint)

    def _response(self, state: TaskState) -> strategy_pb2.RunStrategyResponse:
        ok = state.status == "completed"
        return strategy_pb2.RunStrategyResponse(
            workflow_id=state.workflow_id,
            task_id=state.task_id,
            status=common_pb2.STATUS_CODE_OK if ok else common_pb2.STATUS_CODE_ERROR,
            error_code=strategy_pb2.STRATEGY_ERROR_OK if ok else state.error_code,
            task_status=_STATUS.get(state.status, strategy_pb2.STRATEGY_TASK_STATUS_UNSPECIFIED),
            result=state.result,
            error_message=state.error_message,
            budget=strategy_pb2.Budget(
                token_budget=state.token_budget, tokens_used=state.tokens_used
            ),
        )
