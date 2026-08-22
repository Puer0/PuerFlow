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
        llm_service_url: str = "",
        timeout: float = 60.0,
        mock: bool = False,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.llm_service_url = llm_service_url.rstrip("/")
        self.timeout = timeout
        self.mock = mock or (not api_key and not self.llm_service_url)

    async def generate(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.2,
        tools: list[dict[str, Any]] | None = None,
        *,
        model_tier: str | None = None,
        specific_model: str | None = None,
        provider_override: str | None = None,
        session_id: str | None = None,
    ) -> LLMResponse:
        if self.mock:
            last_user = next((m.get("content") or "" for m in reversed(messages) if m.get("role") == "user"), "")
            return LLMResponse(
                content=f"[sample] {last_user}".strip(),
                model="mock-sample",
                provider="mock",
                usage=LLMUsage(input_tokens=8, output_tokens=8, total_tokens=16),
            )
        if self.llm_service_url:
            return await self._generate_via_llm_service(
                messages,
                temperature=temperature,
                tools=tools,
                model_tier=model_tier,
                specific_model=specific_model,
                provider_override=provider_override,
                session_id=session_id,
            )
        return await self._generate_via_openai(messages, temperature=temperature, tools=tools)

    async def _generate_via_llm_service(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float,
        tools: list[dict[str, Any]] | None,
        model_tier: str | None,
        specific_model: str | None,
        provider_override: str | None,
        session_id: str | None,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "messages": messages,
            "model_tier": (model_tier or "small").lower(),
            "temperature": temperature,
        }
        if specific_model:
            payload["specific_model"] = specific_model
        if tools:
            payload["tools"] = tools
        if provider_override:
            payload["provider_override"] = provider_override
        if session_id:
            payload["session_id"] = session_id
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.llm_service_url}/completions/",
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
        usage = body.get("usage") or {}
        return LLMResponse(
            content=str(body.get("output_text") or body.get("content") or ""),
            model=str(body.get("model") or self.model),
            provider=str(body.get("provider") or "llm-service"),
            usage=LLMUsage(
                input_tokens=int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0),
                output_tokens=int(usage.get("output_tokens") or usage.get("completion_tokens") or 0),
                total_tokens=int(usage.get("total_tokens") or 0),
                cost_usd=float(usage.get("cost_usd") or usage.get("cost") or 0.0),
            ),
            tool_calls=_parse_service_tool_calls(body),
        )

    async def _generate_via_openai(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float,
        tools: list[dict[str, Any]] | None,
    ) -> LLMResponse:
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


def _parse_service_tool_calls(body: dict[str, Any]) -> list[dict[str, Any]]:
    raw = body.get("tool_calls") or body.get("function_calls")
    if raw:
        parsed = _parse_tool_calls(raw)
        if parsed:
            return parsed
        calls: list[dict[str, Any]] = []
        for index, item in enumerate(raw):
            if not isinstance(item, dict):
                continue
            arguments = item.get("arguments") or {}
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments) if arguments else {}
                except json.JSONDecodeError:
                    arguments = {}
            name = item.get("name") or (item.get("function") or {}).get("name") or ""
            if name:
                calls.append({"id": item.get("id") or f"call_{index}", "name": name, "arguments": arguments})
        return calls
    single = body.get("function_call")
    if isinstance(single, dict) and single.get("name"):
        arguments = single.get("arguments") or {}
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments) if arguments else {}
            except json.JSONDecodeError:
                arguments = {}
        return [{"id": single.get("id") or "call_0", "name": single["name"], "arguments": arguments}]
    return []


def _parse_tool_calls(raw: Any) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        function = item.get("function") or {}
        arguments = function.get("arguments") if function else item.get("arguments")
        if arguments is None:
            arguments = "{}"
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments) if arguments else {}
            except json.JSONDecodeError:
                arguments = {}
        name = function.get("name") if function else item.get("name")
        if name:
            calls.append(
                {
                    "id": item.get("id") or "",
                    "name": name,
                    "arguments": arguments,
                }
            )
    return calls
