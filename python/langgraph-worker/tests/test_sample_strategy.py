from puerflow_worker.events import ShannonEvent
from puerflow_worker.llm import CompletionClient
from puerflow_worker.runtime import TaskState
from puerflow_worker.strategies.sample import SampleStrategy


async def test_sample_graph_emits_shannon_events():
    events: list[ShannonEvent] = []

    async def emit(event: ShannonEvent) -> None:
        events.append(event)

    task = TaskState(
        workflow_id="wf-graph",
        task_id="wf-graph",
        strategy="sample",
        query="capital of France",
        session={"history": [{"role": "user", "content": "hi"}]},
    )
    result = await SampleStrategy(CompletionClient(mock=True)).run(task, emit)
    assert "capital of France" in result.content
    assert [item.type for item in events] == [
        "WORKFLOW_STARTED",
        "DELEGATION",
        "AGENT_STARTED",
        "LLM_PROMPT",
        "LLM_OUTPUT",
        "AGENT_COMPLETED",
        "WORKFLOW_COMPLETED",
    ]
