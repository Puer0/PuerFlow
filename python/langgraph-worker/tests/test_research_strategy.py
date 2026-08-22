from puerflow_worker.events import ShannonEvent
from puerflow_worker.llm import CompletionClient
from puerflow_worker.runtime import TaskState
from puerflow_worker.strategies.research import ResearchStrategy, claim_support_score, weakest_claims


def test_claim_overlap_scores_evidence():
    assert claim_support_score("solar farms cut costs", "solar farms cut costs in 2024") > 0.5
    assert weakest_claims(["aaaa uniqueclaimxyz", "solar farms cut costs"], "solar farms cut costs") == ["aaaa uniqueclaimxyz"]


async def test_research_graph_completes():
    events: list[ShannonEvent] = []

    async def emit(event: ShannonEvent) -> None:
        events.append(event)

    task = TaskState(
        workflow_id="wf-research",
        task_id="wf-research",
        strategy="research",
        query="renewable energy",
    )
    result = await ResearchStrategy(CompletionClient(mock=True)).run(task, emit)
    assert result.content
    types = [item.type for item in events]
    assert types[0] == "WORKFLOW_STARTED"
    assert "RESEARCH_PLAN_READY" in types
    assert types[-1] == "WORKFLOW_COMPLETED"


async def test_research_hides_python_executor():
    from puerflow_worker.tools import build_default_registry
    from puerflow_worker.settings import WorkerSettings
    from puerflow_worker.sandbox import SandboxClient

    registry = build_default_registry(SandboxClient(optional=True), WorkerSettings())
    task = TaskState(
        workflow_id="wf-hide",
        task_id="wf-hide",
        strategy="research",
        query="q",
        tools=["calculator", "python_executor"],
    )
    strategy = ResearchStrategy(CompletionClient(mock=True), tools=registry)

    async def emit(event):
        return None

    await strategy.run(task, emit)
    assert "python_executor" not in (task.tools or [])
