from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class LLMUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0

    def as_dict(self) -> dict:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": self.cost_usd,
            "prompt_tokens": self.input_tokens,
            "completion_tokens": self.output_tokens,
        }


@dataclass
class LLMResponse:
    content: str
    model: str = "mock"
    provider: str = "mock"
    usage: LLMUsage = field(default_factory=LLMUsage)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


class CompletionClient:
    def __init__(
        self,
        *,
        api_key: str = "",
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        timeout: float = 60.0,
        mock: bool = False,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.mock = mock or not api_key

    async def generate(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.2,
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        if self.mock:
            last_user = next((m.get("content") or "" for m in reversed(messages) if m.get("role") == "user"), "")
            return LLMResponse(
                content=f"[sample] {last_user}".strip(),
                model="mock-sample",
                provider="mock",
                usage=LLMUsage(input_tokens=8, output_tokens=8, total_tokens=16),
            )

        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
        message = (body.get("choices") or [{}])[0].get("message") or {}
        usage = body.get("usage") or {}
        return LLMResponse(
            content=str(message.get("content") or ""),
            model=body.get("model", self.model),
            provider="openai",
            usage=LLMUsage(
                input_tokens=int(usage.get("prompt_tokens") or 0),
                output_tokens=int(usage.get("completion_tokens") or 0),
                total_tokens=int(usage.get("total_tokens") or 0),
            ),
            tool_calls=_parse_tool_calls(message.get("tool_calls")),
        )


def _parse_tool_calls(raw: Any) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for item in raw or []:
        function = item.get("function") or {}
        arguments = function.get("arguments") or "{}"
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments) if arguments else {}
            except json.JSONDecodeError:
                arguments = {}
        calls.append(
            {
                "id": item.get("id") or "",
                "name": function.get("name") or "",
                "arguments": arguments,
            }
        )
    return calls
