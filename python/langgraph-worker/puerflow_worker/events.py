from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

try:
    from redis.asyncio import Redis
except Exception:  # noqa: BLE001
    Redis = None  # type: ignore[misc, assignment]


def stream_key(workflow_id: str) -> str:
    return f"shannon:workflow:events:{workflow_id}"


def seq_key(workflow_id: str) -> str:
    return f"shannon:workflow:events:{workflow_id}:seq"


@dataclass
class ShannonEvent:
    workflow_id: str
    type: str
    agent_id: str = ""
    message: str = ""
    payload: dict[str, Any] | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    seq: int = 0
    stream_id: str = ""


class ShannonEventPublisher:
    """Writes Shannon-compatible Redis Stream events."""

    def __init__(self, redis_url: str, maxlen: int = 256, optional: bool = True):
        self.redis_url = redis_url
        self.maxlen = maxlen
        self.optional = optional
        self._redis: Any = None
        self._memory: dict[str, list[ShannonEvent]] = {}

    @property
    def using_redis(self) -> bool:
        return self._redis is not None

    async def connect(self) -> None:
        if Redis is None:
            return
        try:
            client = Redis.from_url(self.redis_url, decode_responses=True)
            await client.ping()
            self._redis = client
        except Exception:
            if not self.optional:
                raise
            self._redis = None

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    async def publish(self, event: ShannonEvent) -> ShannonEvent:
        if self._redis is not None:
            event.seq = int(await self._redis.incr(seq_key(event.workflow_id)))
            payload_json = json.dumps(event.payload or {}, ensure_ascii=False)
            event.stream_id = await self._redis.xadd(
                stream_key(event.workflow_id),
                {
                    "workflow_id": event.workflow_id,
                    "type": event.type,
                    "agent_id": event.agent_id,
                    "message": event.message,
                    "payload": payload_json,
                    "ts_nano": str(int(event.timestamp.timestamp() * 1_000_000_000)),
                    "seq": str(event.seq),
                },
                maxlen=self.maxlen,
                approximate=True,
            )
            await self._redis.expire(stream_key(event.workflow_id), 24 * 3600)
            await self._redis.expire(seq_key(event.workflow_id), 48 * 3600)
            return event

        bucket = self._memory.setdefault(event.workflow_id, [])
        event.seq = len(bucket) + 1
        bucket.append(event)
        return event

    def memory_events(self, workflow_id: str) -> list[ShannonEvent]:
        return list(self._memory.get(workflow_id, []))
