from puerflow_worker.events import ShannonEvent
from puerflow_worker.llm import CompletionClient
from puerflow_worker.runtime import TaskState
from puerflow_worker.strategies.swarm import SwarmStrategy, parse_board, ready_tasks


def test_parse_board_and_ready_set():
    board = parse_board(
        '[{"id":"t1","title":"research","owner":"researcher","dependencies":[]},'
        '{"id":"t2","title":"write","owner":"writer","dependencies":["t1"]}]',
        "query",
    )
    assert [item["owner"] for item in board] == ["researcher", "writer"]
    assert [item["id"] for item in ready_tasks(board)] == ["t1"]
    board[0]["done"] = True
    assert [item["id"] for item in ready_tasks(board)] == ["t2"]


async def test_swarm_graph_completes():
    events: list[ShannonEvent] = []

    async def emit(event: ShannonEvent) -> None:
        events.append(event)

    task = TaskState(
        workflow_id="wf-swarm",
        task_id="wf-swarm",
        strategy="swarm",
        query="review the plan",
    )
    result = await SwarmStrategy(CompletionClient(mock=True)).run(task, emit)
    assert result.content
    types = [item.type for item in events]
    assert types[0] == "WORKFLOW_STARTED"
    assert "TEAM_RECRUITED" in types
    assert "LEAD_DECISION" in types
    assert types[-1] == "WORKFLOW_COMPLETED"
    assert types.count("AGENT_STARTED") == 2
