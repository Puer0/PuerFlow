# PuerFlow 方案 B 合体实施规划

> **For agentic workers:** 按任务 checkbox 逐步执行；先契约与接线，再替换策略执行路径，最后联调沙箱与事件流。

**Goal:** 以 Shannon 为骨架，保留 Go Gateway + Go Orchestrator/Temporal + Rust WASI + Session/Qdrant + Desktop；用 AstraFlow 的 LangGraph 策略作为 Python Worker；跨语言契约一次齐，主链路可正常跑通。

**Architecture:** Go 握执行引擎（Temporal 推进/重试/回放）；Python LangGraph 只做具体策略 Worker；Rust Agent Core 做沙箱；控制面 gRPC+proto，事件面 Redis Stream → Gateway SSE。

**Tech Stack:** Go · Temporal · gRPC/Protobuf · Python · LangGraph · Rust/WASI · PostgreSQL · Redis · Qdrant · Docker · Next.js/Tauri Desktop

**工作目录约定:**
- 主仓落地：`D:\PuerFlow`（本规划所在仓）
- 源码来源：`D:\Shannon\Shannon`（编排/沙箱/桌面/基础设施）、`D:\AstraFlow`（LangGraph 策略与相关 Python 能力）
- README 对外只写一句参考 Shannon；**必须保留 LICENSE 与源码版权头**（MIT）

---

## 0. 已定决策（勿再改口径）

| 项 | 决定 |
|---|---|
| 方案 | **B**：Go=编排+执行引擎；Python/LangGraph=策略 Worker；Rust=沙箱 |
| Temporal | **保留** |
| Python 主体 | **AstraFlow LangGraph 策略** 替换 Shannon 原策略执行路径；Shannon `python/` 能删则删、避免双份 Agent 逻辑 |
| 沙箱 | **Shannon Rust Agent Core**（不用 AstraFlow 旧沙箱当主路径） |
| 记忆 | **Session（Postgres/Redis）+ Qdrant**（不上 Milvus） |
| 前端 | **Shannon desktop** |
| 仓范围 | 大骨架可留；砍杂余面试/分析类文档 |
| 控制面 | Go ↔ Python **gRPC** |
| 事件面 | **Redis Stream** → Gateway **SSE**（对齐 Shannon 原事件模型） |
| 合规 | LICENSE + 版权头保留；README 一句「参考 Shannon」 |
| 面试口径 | 编排/沙箱基于 Shannon 代码基础；你做 LangGraph 接入与契约联调 |

---

## 1. 目标运行时拓扑

```
Client / Desktop
    │  HTTP + SSE
    ▼
Go Gateway :8080
    │  gRPC
    ▼
Go Orchestrator :50052  ←→  Temporal :7233
    │
    ├─ gRPC ──► Python LangGraph Worker（AstraFlow 策略）
    │              │
    │              ├─ 写 Redis Stream（事件）
    │              └─ gRPC ──► Rust Agent Core :50051（WASI）
    │
    └─（可选仍由 Go 直调）Rust Agent Core

PostgreSQL / Redis / Qdrant
```

---

## 2. 跨语言契约（尽可能全，一次设计）

### 2.1 控制面（Go ↔ Python，gRPC + proto）

建议新建（或扩展现有 `protos/`）：

| RPC / 能力 | 方向 | 说明 | 主要复用 |
|---|---|---|---|
| `RunStrategy` | Go→Py | strategy、task、session、budget、context | 替换原 Temporal Activity 调 LLM/策略处 |
| `Cancel` | Go→Py | 协作式取消 | Temporal cancel + Worker 内取消 |
| `GetStatus` | Go→Py | 任务/步骤状态 | Gateway 轮询兜底 |
| `ApproveDecision` | Go→Py | 人工审批结果回传 | Shannon 审批 + AstraFlow review |
| `BudgetReport` / 触阈信号 | Py→Go 或双向 | Token 用量、降级/硬停 | Shannon budget + AstraFlow budget |
| `InjectSessionContext` | Go→Py | Session + Qdrant 检索注入 | Shannon hierarchical memory |
| `Health/Ready` | 探测 | Worker 就绪 | K8s/Compose healthcheck |
| `FailoverHint` | Py→Go | 策略失败建议换路 | Orchestrator 降级 |

### 2.2 沙箱（Python/Go ↔ Rust，复用现有 proto）

| 能力 | 说明 | 复用 |
|---|---|---|
| `ExecSandbox` / SandboxService | staging 执行、结果回传 | `protos/sandbox/`、`protos/agent/` |
| `WorkspaceSync` | 文件进出 workspace | Shannon session workspace |

### 2.3 事件面（Redis Stream）

| 能力 | 说明 | 复用 |
|---|---|---|
| 事件写入 | progress / tool_call / llm_output / completed / failed… | Shannon Streaming + Redis Stream ID |
| 续传 | `last_stream_id` | `streaming.proto` |
| 对外 | Gateway SSE | Shannon Gateway HTTP streaming |

**原则：** 不新造第二套事件总线；字段对齐 Shannon 现有 `TaskUpdate` / SSE 类型，Desktop 才能少改。

---

## 3. 目录与模块落地（建议）

在 `D:\PuerFlow` 中建议结构（从 Shannon 拷贝后调整）：

```
PuerFlow/
  LICENSE                 # 保留 Kocoro MIT + 本项目声明
  README.md               # 一句参考 Shannon + 如何启动
  protos/                 # 扩展 strategy worker proto
  go/                     # Gateway + Orchestrator（改 Activity）
  rust/                   # Agent Core（主路径复用）
  python/
    langgraph-worker/     # 从 AstraFlow 迁入的策略服务（新）
    # 原 llm-service：逐步瘦身或删除被替代部分
  desktop/                # Shannon desktop
  deploy/compose/         # 增加 langgraph-worker 服务
  docs/
    方案B-合体实施规划.md  # 本文件
```

**从 AstraFlow 迁入（优先）：**
- `src/astra_flow/workflows/`（sample/dag/research/swarm/registry…）
- 支撑策略所需：`tools/`、`llm/`、`budget/` 中 Worker 依赖部分
- 沙箱客户端改为调 Shannon Rust（替换原 WASI HTTP 客户端）

**从 Shannon 保留（优先）：**
- `go/orchestrator`、`go` Gateway
- `rust/agent-core`
- Temporal 工作流骨架（Activity 改为调 LangGraph Worker）
- Session / Qdrant / Redis Stream / Desktop / Compose

**可砍杂余：**
- 两边简历/面经/亮点分析等中文面试 md（不进运行时）
- 重复的 ROADMAP 宣传稿可精简；保留能指导开发的 docs

---

## 4. 实施任务（按序）

### Task 1: 初始化 PuerFlow 主仓骨架

**Files:**
- Create: `D:\PuerFlow\` 从 Shannon 同步核心目录
- Keep: `LICENSE`、源码版权头
- Create: `README.md`（一句参考 + 启动方式）

- [ ] **Step 1:** 复制 Shannon 必要目录到 `D:\PuerFlow`（go/rust/protos/desktop/deploy/config/scripts…）
- [ ] **Step 2:** 确认根目录 `LICENSE` 存在且未删版权头
- [ ] **Step 3:** README 只写参考句 + 本方案拓扑 + `make dev`/`compose` 入口
- [ ] **Step 4:** 去掉杂余面试文档；保留本规划

**验收:** 目录可 `compose` 起来（即使策略仍是旧路径）

---

### Task 2: 定义 Strategy Worker proto

**Files:**
- Create: `protos/strategy/strategy.proto`（名称可调整）
- Modify: `Makefile` / `make proto` 生成 Go+Python stub

- [ ] **Step 1:** 写入 RunStrategy / Cancel / GetStatus / ApproveDecision / Health 等 RPC 与消息字段
- [ ] **Step 2:** 生成 Go、Python 代码
- [ ] **Step 3:** 合同评审：字段覆盖 session、budget、strategy enum、error code

**验收:** `make proto` 成功；Go/Python 都能 import

---

### Task 3: 落地 Python LangGraph Worker 服务

**Files:**
- Create: `python/langgraph-worker/`（FastAPI 或 grpc 服务入口）
- Copy/Adapt: AstraFlow `workflows/*`、`tools/*`、必要依赖
- Modify: 沙箱调用改为 Shannon Rust gRPC 客户端

- [ ] **Step 1:** 最小 gRPC/HTTP 服务壳 + Health
- [ ] **Step 2:** 接入 `RunStrategy` → registry 分发 sample/dag/research/swarm
- [ ] **Step 3:** 事件写入 Redis Stream（字段对齐 Shannon）
- [ ] **Step 4:** Cancel 协作取消接到图执行循环
- [ ] **Step 5:** BudgetReport / 触阈与审批回调接通
- [ ] **Step 6:** ExecSandbox 走 Rust Agent Core

**验收:** 单测或 grpcurl：RunStrategy 能跑通至少 Sample；事件能在 Redis 看到

---

### Task 4: 改 Go Temporal Activity 指向 Worker

**Files:**
- Modify: `go/orchestrator/internal/activities/*`（原调 LLM service / 策略处）
- Modify: 相关 workflows strategies，使「执行智能图」经 Activity→LangGraph Worker
- Keep: Temporal 工作流控制、预算、session 注入在 Go

- [ ] **Step 1:** 新增 Activity 客户端封装（gRPC → LangGraph Worker）
- [ ] **Step 2:** 选一条主策略（建议 Sample/Simple）切流验证
- [ ] **Step 3:** 依次切 DAG / Research / Swarm
- [ ] **Step 4:** Cancel、审批、FailoverHint 与 Temporal 重试策略对齐
- [ ] **Step 5:** 逐步停用被替代的 Shannon Python 策略路径

**验收:** 提交任务后 Temporal UI 可见工作流；策略结果从 Worker 返回

---

### Task 5: 事件链路与 Desktop

**Files:**
- Modify: Gateway SSE（若字段有 diff 则适配）
- Verify: desktop 订阅与时间线展示

- [ ] **Step 1:** 确认 Redis Stream 事件类型与 Desktop 过滤器兼容
- [ ] **Step 2:** SSE 续传 `last_stream_id` 可用
- [ ] **Step 3:** Desktop 跑一条任务能看到 tool/进度/完成

**验收:** Desktop 或 curl SSE 完整看到一轮执行

---

### Task 6: 沙箱 E2E

**Files:**
- Modify: LangGraph tool `python_executor`（或等价）→ Rust
- Verify: staging / 回写 / 超时

- [ ] **Step 1:** 工具调用触发 WASI 执行
- [ ] **Step 2:** 失败/超时事件进 Stream
- [ ] **Step 3:** 审批门禁（若高危）走 ApproveDecision

**验收:** 含代码执行的任务在沙箱内跑通并回传

---

### Task 7: Compose / 配置 / 回归

**Files:**
- Modify: `deploy/compose/docker-compose.yml` 增加 `langgraph-worker`
- Modify: `.env.example`、`config/*.yaml`
- Test: smoke / 关键路径手工清单

- [ ] **Step 1:** 一键拉起 Gateway/Orchestrator/Temporal/Postgres/Redis/Qdrant/Rust/Worker/Desktop 依赖
- [ ] **Step 2:** smoke：submit → stream → result
- [ ] **Step 3:** 回归：cancel、budget 触阈、session 多轮、Qdrant 语义注入（若开启）
- [ ] **Step 4:** 文档：架构图 + 契约表 + 已知边界（pause 等若未做则写明）

**验收:** 按 README 冷启动可演示；主功能清单打勾

---

## 5. 功能「尽可能全」检查清单（验收用）

- [ ] 任务提交 / 查询 / 列表
- [ ] Temporal 推进与失败重试
- [ ] 策略：轻量单轮 / DAG / Research / Swarm（按 AstraFlow 能力对齐）
- [ ] Redis Stream 事件 + Gateway SSE + Desktop 展示
- [ ] Cancel
- [ ] 人工审批
- [ ] Token 预算与触阈
- [ ] Session 连续
- [ ] Qdrant 语义记忆（按配置开启）
- [ ] Rust WASI 代码执行
- [ ] Health 探测
- [ ] LICENSE / 版权头完整

---

## 6. 风险与诚实边界

1. **不是两仓拷贝即用**：核心工作量在 Activity↔Worker 契约与沙箱改接。  
2. **Cancel / 部分 API**：AstraFlow 原弱项需在 Worker 内补齐，不能假设自动变强。  
3. **双 Python 并存是过渡态**：最终应收敛到 langgraph-worker。  
4. **面试**：仓内有 Shannon 代码指纹属正常；口径必须是「基于 Shannon + LangGraph 接入」，禁止「从零独立复现全部 Go/Rust」。  

---

## 7. 建议执行顺序（给人看的）

```
Task1 骨架 → Task2 proto → Task3 Worker(Sample)
  → Task4 Go 切 Sample → Task5 事件/Desktop
  → Task3/4 扩 DAG/Research/Swarm → Task6 沙箱 → Task7 Compose 回归
```

---

## 8. 分支路线图（一模块一分支）

**节奏：** 本地完成一个可验收小模块 → 提交并 `push` 对应功能分支到 `https://github.com/Puer0/PuerFlow.git`。  
**命名：** `feat/序号-中文名`（两位序号）。未经明确说合入 `main` 前，只推功能分支。  
**目标：** 约 30–40 个分支；下列 38 条为默认切分。

### 骨架 / 合规（01–05）

| 分支 | 对应 |
|---|---|
| `feat/01-仓库骨架` | Task1：从 Shannon 同步核心目录到 `D:\PuerFlow` |
| `feat/02-许可证与版权头` | 保留 LICENSE / 源码版权头 |
| `feat/03-README参考说明` | README 一句参考 Shannon + 启动入口 |
| `feat/04-清理杂余文档` | 砍面试/分析类杂余 md |
| `feat/05-Compose基线可启动` | Compose 基线能起来（策略可仍为旧路径） |

### 契约 Proto（06–10）

| 分支 | 对应 |
|---|---|
| `feat/06-策略RunStrategy契约` | RunStrategy RPC/消息 |
| `feat/07-取消与状态查询契约` | Cancel / GetStatus |
| `feat/08-审批与预算契约` | ApproveDecision / BudgetReport |
| `feat/09-健康检查与失败降级契约` | Health/Ready / FailoverHint |
| `feat/10-生成Proto代码` | `make proto` 生成 Go+Python stub |

### LangGraph Worker（11–18）

| 分支 | 对应 |
|---|---|
| `feat/11-LangGraph服务壳` | Worker 服务壳 + Health |
| `feat/12-迁入Sample策略` | AstraFlow Sample → Worker |
| `feat/13-迁入DAG策略` | DAG |
| `feat/14-迁入Research策略` | Research |
| `feat/15-迁入Swarm策略` | Swarm |
| `feat/16-Redis-Stream事件` | 事件写入对齐 Shannon |
| `feat/17-Worker协作取消` | Cancel 接到图循环 |
| `feat/18-Worker预算与审批` | Budget / Approve 接通 |

### Go / Temporal 接线（19–25）

| 分支 | 对应 |
|---|---|
| `feat/19-Go的gRPC客户端` | Activity 调 Worker 客户端封装 |
| `feat/20-接通Sample到Temporal` | Sample/Simple 切流 |
| `feat/21-接通DAG到Temporal` | DAG |
| `feat/22-接通Research到Temporal` | Research |
| `feat/23-接通Swarm到Temporal` | Swarm |
| `feat/24-Temporal取消对齐` | Cancel 与 Temporal 对齐 |
| `feat/25-下线旧Python路径` | 停用被替代的 Shannon Python 策略路径 |

### 沙箱（26–29）

| 分支 | 对应 |
|---|---|
| `feat/26-Rust沙箱客户端` | Worker 侧调 Agent Core |
| `feat/27-工具调用ExecSandbox` | 工具路径走 WASI |
| `feat/28-Workspace文件同步` | staging ↔ workspace |
| `feat/29-沙箱端到端` | 含代码执行任务 E2E |

### 事件 / 前端 / 记忆（30–34）

| 分支 | 对应 |
|---|---|
| `feat/30-Gateway-SSE对齐` | SSE / stream_id 续传 |
| `feat/31-Desktop冒烟` | Desktop 看一轮执行 |
| `feat/32-Session上下文注入` | Session 注入策略 |
| `feat/33-Qdrant语义记忆` | Qdrant 检索注入（按配置） |
| `feat/34-鉴权上下文透传` | AuthContext 透传 |

### 收尾（35–38）

| 分支 | 对应 |
|---|---|
| `feat/35-Compose加入Worker` | compose 增加 langgraph-worker |
| `feat/36-提交到流式结果冒烟` | submit → stream → result |
| `feat/37-取消与预算回归` | cancel / budget 触阈回归 |
| `feat/38-架构与契约文档` | 架构图 + 契约表 + 已知边界 |

**开干顺序：** 从 `feat/01-仓库骨架` 起，严格按序号；中途若某步过大，可再拆 `feat/12a-…`，但尽量保持「一分支一验收」。

---

## 9. 下一步

规划已就绪。开始落地时建议从 **`feat/01-仓库骨架`**（Task 1）开工，并单独开会话执行，避免一次改爆。
