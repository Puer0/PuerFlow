# LangGraph strategy worker

gRPC service on `:50053`. Stubs: `puerflow_worker/grpc_gen` (from `make proto`).

Compose service: `langgraph-worker`. Orchestrator reaches it when `LANGGRAPH_WORKER_ENABLED=1`.

```bash
PYTHONPATH=python/langgraph-worker:python/langgraph-worker/puerflow_worker/grpc_gen \
  python -m puerflow_worker.server
```
