from puerflow_worker.events import ShannonEvent
from puerflow_worker.llm import CompletionClient
from puerflow_worker.runtime import TaskState
from puerflow_worker.strategies.dag import DagStrategy, split_subtasks


def test_split_subtasks():
    parts = split_subtasks("alpha; beta")
    assert parts == ["alpha", "beta"]


async def test_dag_graph_completes():
    events: list[ShannonEvent] = []

    async def emit(event: ShannonEvent) -> None:
        events.append(event)

    task = TaskState(
        workflow_id="wf-dag",
        task_id="wf-dag",
        strategy="dag",
        query="alpha; beta",
    )
    result = await DagStrategy(CompletionClient(mock=True)).run(task, emit)
    assert result.content
    types = [item.type for item in events]
    assert types[0] == "WORKFLOW_STARTED"
    assert types[-1] == "WORKFLOW_COMPLETED"
    assert types.count("AGENT_STARTED") == 2
