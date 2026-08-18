from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = Field(default="puerflow-langgraph-worker")
    version: str = Field(default="0.1.0")
    grpc_host: str = Field(default="0.0.0.0")
    grpc_port: int = Field(default=50053)
    redis_url: str = Field(default="redis://localhost:6379/0")
    redis_optional: bool = Field(default=True)
    stream_maxlen: int = Field(default=256)
    agent_core_addr: str = Field(default="agent-core:50051")


@lru_cache
def get_settings() -> WorkerSettings:
    return WorkerSettings()
