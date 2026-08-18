# LangGraph strategy worker

gRPC service on `:50053`. Stubs: `puerflow_worker/grpc_gen` (from `make proto`).

```bash
PYTHONPATH=python/langgraph-worker:python/langgraph-worker/puerflow_worker/grpc_gen \
  python -m puerflow_worker.server
```
