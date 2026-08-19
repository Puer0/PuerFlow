from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "puerflow_worker" / "grpc_gen"))

from common import common_pb2
from strategy import strategy_pb2

from puerflow_worker.events import ShannonEventPublisher
from puerflow_worker.llm import CompletionClient
from puerflow_worker.runtime import TaskRegistry
from puerflow_worker.servicer import StrategyWorkerServicer
from puerflow_worker.settings import WorkerSettings
from puerflow_worker.strategies.dag import DagStrategy
from puerflow_worker.strategies.research import ResearchStrategy
from puerflow_worker.strategies.sample import SampleStrategy
from puerflow_worker.strategies.swarm import SwarmStrategy


def _svc() -> StrategyWorkerServicer:
    publisher = ShannonEventPublisher("redis://localhost:6379/0", optional=True)
    llm = CompletionClient(mock=True)
    return StrategyWorkerServicer(
        TaskRegistry(publisher),
        WorkerSettings(),
        {
            "sample": SampleStrategy(llm),
            "dag": DagStrategy(llm),
            "research": ResearchStrategy(llm),
            "swarm": SwarmStrategy(llm),
        },
    )


async def test_health_ready():
    svc = _svc()
    health = await svc.Health(strategy_pb2.HealthRequest(), None)
    assert health.healthy is True
    ready = await svc.Ready(strategy_pb2.ReadyRequest(), None)
    assert ready.ready is True


async def test_run_strategy_sample_emits_events():
    svc = _svc()
    req = strategy_pb2.RunStrategyRequest(
        workflow_id="wf-sample-1",
        query="What is 2+2?",
        strategy=strategy_pb2.STRATEGY_KIND_SAMPLE,
    )
    resp = await svc.RunStrategy(req, None)
    assert resp.task_status == strategy_pb2.STRATEGY_TASK_STATUS_COMPLETED
    assert resp.status == common_pb2.STATUS_CODE_OK
    assert "[sample]" in resp.result
    events = svc.registry.publisher.memory_events("wf-sample-1")
    types = [item.type for item in events]
    assert "WORKFLOW_STARTED" in types
    assert "WORKFLOW_COMPLETED" in types
    assert "LLM_OUTPUT" in types


async def test_get_status_and_budget():
    svc = _svc()
    await svc.RunStrategy(
        strategy_pb2.RunStrategyRequest(
            workflow_id="wf-status",
            query="hello",
            strategy=strategy_pb2.STRATEGY_KIND_SIMPLE,
            budget=strategy_pb2.Budget(token_budget=1000),
        ),
        None,
    )
    status = await svc.GetStatus(strategy_pb2.GetStatusRequest(workflow_id="wf-status"), None)
    assert status.result
    dag = await svc.RunStrategy(
        strategy_pb2.RunStrategyRequest(
            workflow_id="wf-dag-rpc",
            query="alpha; beta",
            strategy=strategy_pb2.STRATEGY_KIND_DAG,
        ),
        None,
    )
    assert dag.task_status == strategy_pb2.STRATEGY_TASK_STATUS_COMPLETED
    assert dag.result
    budget = await svc.BudgetReport(strategy_pb2.BudgetReportRequest(workflow_id="wf-status"), None)
    assert budget.task_budget.token_budget == 1000


async def test_inject_session_and_failover():
    svc = _svc()
    injected = await svc.InjectSessionContext(
        strategy_pb2.InjectSessionContextRequest(
            workflow_id="wf-session",
            session=strategy_pb2.SessionPayload(
                session_id="s1",
                history=[strategy_pb2.ConversationMessage(role="user", content="hi")],
            ),
        ),
        None,
    )
    assert injected.applied is True
    assert injected.history_messages == 1
    hint = await svc.GetFailoverHint(
        strategy_pb2.GetFailoverHintRequest(
            last_error=strategy_pb2.STRATEGY_ERROR_STRATEGY_FAILED,
            failed_strategy=strategy_pb2.STRATEGY_KIND_SWARM,
        ),
        None,
    )
    assert hint.hint.should_failover is True
    assert hint.hint.suggested_strategy == strategy_pb2.STRATEGY_KIND_SAMPLE
    sample_hint = await svc.GetFailoverHint(
        strategy_pb2.GetFailoverHintRequest(
            last_error=strategy_pb2.STRATEGY_ERROR_STRATEGY_FAILED,
            failed_strategy=strategy_pb2.STRATEGY_KIND_SAMPLE,
        ),
        None,
    )
    assert sample_hint.hint.should_failover is False
    budget_hint = await svc.GetFailoverHint(
        strategy_pb2.GetFailoverHintRequest(
            last_error=strategy_pb2.STRATEGY_ERROR_BUDGET_EXCEEDED,
            failed_strategy=strategy_pb2.STRATEGY_KIND_DAG,
        ),
        None,
    )
    assert budget_hint.hint.should_failover is False


async def test_failed_strategy_includes_failover_hint():
    class Boom:
        name = "dag"

        async def run(self, state, emit):
            raise RuntimeError("graph exploded")

    publisher = ShannonEventPublisher("redis://localhost:6379/0", optional=True)
    svc = StrategyWorkerServicer(
        TaskRegistry(publisher),
        WorkerSettings(),
        {"dag": Boom()},
    )
    resp = await svc.RunStrategy(
        strategy_pb2.RunStrategyRequest(
            workflow_id="wf-boom",
            query="fail please",
            strategy=strategy_pb2.STRATEGY_KIND_DAG,
        ),
        None,
    )
    assert resp.error_code == strategy_pb2.STRATEGY_ERROR_STRATEGY_FAILED
    assert resp.failover.should_failover is True
    assert resp.failover.suggested_strategy == strategy_pb2.STRATEGY_KIND_SAMPLE


async def test_budget_hard_stop():
    svc = _svc()
    resp = await svc.RunStrategy(
        strategy_pb2.RunStrategyRequest(
            workflow_id="wf-budget",
            query="hello",
            strategy=strategy_pb2.STRATEGY_KIND_SAMPLE,
            budget=strategy_pb2.Budget(token_budget=1),
        ),
        None,
    )
    assert resp.error_code == strategy_pb2.STRATEGY_ERROR_BUDGET_EXCEEDED
    assert resp.task_status == strategy_pb2.STRATEGY_TASK_STATUS_FAILED


async def test_cancel_rpc_interrupts_running_task():
    from puerflow_worker.llm import LLMResponse, LLMUsage

    class SlowLLM(CompletionClient):
        async def generate(self, messages, temperature=0.2, tools=None):
            await asyncio.sleep(0.3)
            return LLMResponse(content="slow", usage=LLMUsage(total_tokens=1))

    publisher = ShannonEventPublisher("redis://localhost:6379/0", optional=True)
    svc = StrategyWorkerServicer(
        TaskRegistry(publisher),
        WorkerSettings(),
        {"sample": SampleStrategy(SlowLLM(mock=True))},
    )
    req = strategy_pb2.RunStrategyRequest(
        workflow_id="wf-cancel",
        query="please wait",
        strategy=strategy_pb2.STRATEGY_KIND_SAMPLE,
    )

    async def cancel_soon():
        await asyncio.sleep(0.05)
        return await svc.Cancel(
            strategy_pb2.CancelRequest(workflow_id="wf-cancel", reason="stop"),
            None,
        )

    resp, cancelled = await asyncio.gather(svc.RunStrategy(req, None), cancel_soon())
    assert cancelled.accepted is True
    assert resp.error_code == strategy_pb2.STRATEGY_ERROR_CANCELLED


async def test_approval_reject():
    svc = _svc()
    req = strategy_pb2.RunStrategyRequest(
        workflow_id="wf-approve",
        query="needs review",
        strategy=strategy_pb2.STRATEGY_KIND_SAMPLE,
        require_approval=True,
    )

    async def reject():
        await asyncio.sleep(0.05)
        return await svc.ApproveDecision(
            strategy_pb2.ApproveDecisionRequest(
                workflow_id="wf-approve", approved=False, comment="no"
            ),
            None,
        )

    resp, decision = await asyncio.gather(svc.RunStrategy(req, None), reject())
    assert decision.applied is True
    assert resp.error_code == strategy_pb2.STRATEGY_ERROR_CANCELLED
