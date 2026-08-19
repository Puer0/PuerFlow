from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolMetadata:
    name: str
    description: str
    category: str = "general"
    source: str = "native"
    timeout_seconds: float = 30.0
    enabled: bool = True
    dangerous: bool = False
    rate_limit_per_minute: int | None = None
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    success: bool
    output: Any = None
    text: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    execution_time_ms: int | None = None


class Tool(ABC):
    metadata: ToolMetadata

    @abstractmethod
    async def execute(self, parameters: dict[str, Any]) -> ToolResult:
        raise NotImplementedError

    def schema(self) -> dict[str, Any]:
        return {
            "name": self.metadata.name,
            "description": self.metadata.description,
            "category": self.metadata.category,
            "source": self.metadata.source,
            "dangerous": self.metadata.dangerous,
            "parameters": self.metadata.parameters,
        }

    def openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.metadata.name,
                "description": self.metadata.description,
                "parameters": self.metadata.parameters
                or {"type": "object", "properties": {}},
            },
        }
