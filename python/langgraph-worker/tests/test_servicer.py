from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "puerflow_worker" / "grpc_gen"))

from common import common_pb2
from strategy import strategy_pb2

from puerflow_worker.events import ShannonEventPublisher
from puerflow_worker.runtime import TaskRegistry
from puerflow_worker.servicer import StrategyWorkerServicer
from puerflow_worker.settings import WorkerSettings


def _svc() -> StrategyWorkerServicer:
    publisher = ShannonEventPublisher("redis://localhost:6379/0", optional=True)
    return StrategyWorkerServicer(TaskRegistry(publisher), WorkerSettings())


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
    assert [item.type for item in events] == ["WORKFLOW_STARTED", "WORKFLOW_COMPLETED"]


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
