from puerflow_worker.events import ShannonEvent
from puerflow_worker.llm import CompletionClient
from puerflow_worker.runtime import TaskState
from puerflow_worker.strategies.dag import DagStrategy, planned_subtasks, split_subtasks


def test_split_subtasks():
    parts = split_subtasks("alpha; beta")
    assert parts == ["alpha", "beta"]


def test_planned_subtasks_prefer_orchestrator_plan():
    task = TaskState(
        workflow_id="wf",
        task_id="wf",
        strategy="dag",
        query="ignore this; split",
        context={
            "preplanned_subtasks": [
                {"id": "a", "description": "first", "dependencies": []},
                {"id": "b", "description": "second", "dependencies": ["a"]},
            ]
        },
    )
    steps = planned_subtasks(task)
    assert [item["id"] for item in steps] == ["a", "b"]
    assert steps[1]["dependencies"] == ["a"]


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
