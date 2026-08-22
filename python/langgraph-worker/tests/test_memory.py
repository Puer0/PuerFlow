from puerflow_worker.runtime import TaskState
from puerflow_worker.strategies.memory import memory_messages


def test_memory_messages_include_history_and_hits():
    task = TaskState(
        workflow_id="wf",
        task_id="wf",
        strategy="dag",
        query="q",
        session={
            "history": [{"role": "user", "content": "yesterday"}],
            "qdrant_hits": [{"content": "related note"}],
        },
        context={"agent_memory": [{"text": "old"}]},
    )
    messages = memory_messages(task)
    assert any("yesterday" in item["content"] for item in messages)
    assert any(item["content"].startswith("memory:") for item in messages)
    assert any("session memory" in item["content"] for item in messages)
