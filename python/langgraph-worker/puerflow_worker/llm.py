from __future__ import annotations

from dataclasses import dataclass, field

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

    async def generate(self, messages: list[dict[str, str]], temperature: float = 0.2) -> LLMResponse:
        if self.mock:
            last_user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
            return LLMResponse(
                content=f"[sample] {last_user}".strip(),
                model="mock-sample",
                provider="mock",
                usage=LLMUsage(input_tokens=8, output_tokens=8, total_tokens=16),
            )

        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                },
            )
            response.raise_for_status()
            payload = response.json()
        choice = payload["choices"][0]["message"]["content"]
        usage = payload.get("usage") or {}
        return LLMResponse(
            content=choice,
            model=payload.get("model", self.model),
            provider="openai",
            usage=LLMUsage(
                input_tokens=int(usage.get("prompt_tokens") or 0),
                output_tokens=int(usage.get("completion_tokens") or 0),
                total_tokens=int(usage.get("total_tokens") or 0),
            ),
        )
