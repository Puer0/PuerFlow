from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

from puerflow_worker.budget import add_tokens, raise_if_cancelled, raise_if_over_budget
from puerflow_worker.events import ShannonEvent
from puerflow_worker.llm import CompletionClient, LLMResponse
from puerflow_worker.runtime import TaskState
from puerflow_worker.tools.registry import ToolRegistry

EmitFn = Callable[[ShannonEvent], Awaitable[None]]


async def complete_turn(
    llm: CompletionClient,
    tools: ToolRegistry | None,
    task: TaskState,
    emit: EmitFn,
    messages: list[dict[str, Any]],
    *,
    max_rounds: int = 4,
) -> LLMResponse:
    if tools is None:
        response = await llm.generate(messages)
        add_tokens(task, response.usage.total_tokens)
        return response
    return await run_llm_with_tools(llm, tools, task, emit, messages, max_rounds=max_rounds)


async def run_llm_with_tools(
    llm: CompletionClient,
    tools: ToolRegistry,
    task: TaskState,
    emit: EmitFn,
    messages: list[dict[str, Any]],
    *,
    max_rounds: int = 4,
) -> LLMResponse:
    names = list(task.tools) if task.tools else None
    openai_tools = tools.openai_tools(names)
    history = list(messages)
    last = LLMResponse(content="")
    for _ in range(max_rounds):
        raise_if_cancelled(task)
        raise_if_over_budget(task)
        last = await llm.generate(history, tools=openai_tools or None)
        add_tokens(task, last.usage.total_tokens)
        if not last.tool_calls:
            return last
        history.append(
            {
                "role": "assistant",
                "content": last.content or None,
                "tool_calls": [
                    {
                        "id": item.get("id") or f"call_{index}",
                        "type": "function",
                        "function": {
                            "name": item.get("name"),
                            "arguments": json.dumps(item.get("arguments") or {}),
                        },
                    }
                    for index, item in enumerate(last.tool_calls)
                ],
            }
        )
        for index, call in enumerate(last.tool_calls):
            raise_if_cancelled(task)
            name = str(call.get("name") or "")
            arguments = call.get("arguments") or {}
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments) if arguments else {}
                except json.JSONDecodeError:
                    arguments = {}
            result = await tools.execute(name, arguments, task=task, emit=emit)
            observation = result.text or result.error or json.dumps(result.output, default=str)
            history.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id") or f"call_{index}",
                    "name": name,
                    "content": observation[:4000],
                }
            )
    return last
