# PuerFlow

参考 [Shannon](https://github.com/Kocoro-lab/Shannon) 的编排、沙箱与桌面骨架；策略执行接入 AstraFlow LangGraph Worker。

## 运行时拓扑

```
Client / Desktop
    │  HTTP + SSE
    ▼
Go Gateway :8080
    │  gRPC
    ▼
Go Orchestrator :50052  ←→  Temporal :7233
    │
    ├─ gRPC ──► Python LangGraph Worker :50053
    │              │
    │              ├─ 写 Redis Stream（事件）
    │              └─ gRPC ──► Rust Agent Core :50051（WASI）
    │
    └─（LANGGRAPH_WORKER_ENABLED=0 时回退）原 llm-service / ExecuteAgent

PostgreSQL / Redis / Qdrant（可选 profile）
```

`LANGGRAPH_WORKER_ENABLED=1` 时 Simple / DAG / Research / Swarm 走 LangGraph Worker。契约与边界见 [docs/架构与契约.md](docs/架构与契约.md)。

## 启动

先配置环境变量：

```bash
cp .env.example .env
# 填入至少一个 LLM API Key，例如 OPENAI_API_KEY
# 无 Key 时可设 MOCK_LLM=true 做 Worker 冒烟
```

Linux / macOS / Git Bash：

```bash
make setup-env    # 将 .env 链接到 deploy/compose/.env
make setup        # 生成 protobuf stubs（如尚未生成）
make dev          # docker compose 拉起全栈
```

Windows PowerShell（无 `ln` 时手动复制）：

```powershell
Copy-Item .env.example .env
Copy-Item .env deploy\compose\.env
docker compose -f deploy/compose/docker-compose.yml up -d --build
```

常用入口：

| 入口 | 说明 |
|---|---|
| `make dev` | `deploy/compose/docker-compose.yml` 全栈（不含 browser profile） |
| `make down` | 停止并清理 volume |
| `make logs` / `make ps` | 日志与进程 |
| Temporal UI | http://localhost:8088 |
| Gateway | http://localhost:8080 |
| Desktop | `cd desktop && npm run dev` → http://localhost:3000 |
| Qdrant | `docker compose --profile qdrant up -d` → :6333 |

提交一条任务：

```bash
curl -X POST http://localhost:8080/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the capital of France?", "session_id": "demo"}'
```

## 许可

MIT。Shannon 原版权声明见 [LICENSE](LICENSE)。

实施规划：[docs/方案B-合体实施规划.md](docs/方案B-合体实施规划.md)
