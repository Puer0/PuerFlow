from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

_GRPC_GEN = Path(__file__).resolve().parent / "grpc_gen"
if str(_GRPC_GEN) not in sys.path:
    sys.path.insert(0, str(_GRPC_GEN))

import grpc
from strategy import strategy_pb2_grpc

from puerflow_worker.events import ShannonEventPublisher
from puerflow_worker.llm import CompletionClient
from puerflow_worker.runtime import TaskRegistry
from puerflow_worker.servicer import StrategyWorkerServicer
from puerflow_worker.settings import WorkerSettings, get_settings
from puerflow_worker.strategies.dag import DagStrategy
from puerflow_worker.strategies.sample import SampleStrategy

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("puerflow-worker")


async def serve(settings: WorkerSettings | None = None) -> None:
    settings = settings or get_settings()
    publisher = ShannonEventPublisher(
        settings.redis_url,
        maxlen=settings.stream_maxlen,
        optional=settings.redis_optional,
    )
    await publisher.connect()
    registry = TaskRegistry(publisher)
    llm = CompletionClient(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.openai_model,
        mock=settings.mock_llm,
    )
    servicer = StrategyWorkerServicer(
        registry,
        settings,
        SampleStrategy(llm),
        DagStrategy(llm),
    )

    server = grpc.aio.server()
    strategy_pb2_grpc.add_StrategyWorkerServicer_to_server(servicer, server)
    bind = f"{settings.grpc_host}:{settings.grpc_port}"
    server.add_insecure_port(bind)
    logger.info("LangGraph worker listening on %s", bind)
    await server.start()
    try:
        await server.wait_for_termination()
    finally:
        await publisher.close()


def main() -> None:
    asyncio.run(serve())


if __name__ == "__main__":
    main()
