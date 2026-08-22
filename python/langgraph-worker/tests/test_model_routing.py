from puerflow_worker.budget import degrade_model_tier
from puerflow_worker.runtime import TaskState
from puerflow_worker.tools.loop import resolve_completion_options


def test_degrade_model_tier_steps_down_near_budget():
    task = TaskState(workflow_id="wf", task_id="wf", strategy="sample", query="q", tokens_used=80, token_budget=100)
    assert degrade_model_tier("large", task) == "medium"
    assert degrade_model_tier("medium", task) == "small"
    assert degrade_model_tier("small", task) == "small"
    fresh = TaskState(workflow_id="wf", task_id="wf", strategy="sample", query="q", tokens_used=10, token_budget=100)
    assert degrade_model_tier("large", fresh) == "large"


def test_resolve_completion_options_uses_stage_and_provider_override():
    task = TaskState(
        workflow_id="wf",
        task_id="wf",
        strategy="research",
        query="q",
        session={"session_id": "sess-1"},
        context={
            "model_tier": "medium",
            "synthesis_model_tier": "large",
            "provider_override": "openai",
        },
    )
    assert resolve_completion_options(task)["model_tier"] == "medium"
    assert resolve_completion_options(task, "utility")["model_tier"] == "small"
    synthesis = resolve_completion_options(task, "synthesis")
    assert synthesis["model_tier"] == "large"
    assert synthesis["provider_override"] == "openai"
    assert synthesis["session_id"] == "sess-1"

    task.tokens_used = 90
    task.token_budget = 100
    assert resolve_completion_options(task, "synthesis")["model_tier"] == "medium"
