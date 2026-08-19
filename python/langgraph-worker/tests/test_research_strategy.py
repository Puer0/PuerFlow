from puerflow_worker.events import ShannonEvent
from puerflow_worker.llm import CompletionClient
from puerflow_worker.runtime import TaskState
from puerflow_worker.strategies.research import ResearchStrategy


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
