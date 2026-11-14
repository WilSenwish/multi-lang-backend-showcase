# Multi-Lang-Backend-Showcase

> **Java 后端工程师视角，横向对比 Java / Go / Python / Rust / TS(Node.js)**
> 
> 同一个业务场景，提供 5 套可运行的工程实现，对比语言设计哲学、并发模型、错误处理、依赖管理、部署方式、选型取舍。
> 
> **不是语法教程 —— 聚焦工程实践、技术选型、踩坑点。**

---

## 🌟 为什么这个仓库有价值

市面上的语言学习资源要么是纯语法教程，要么是单独某门语言的文档。**缺少一份「Java 工程师视角，同场景多语言工程对比」的参考资料。**

- 同一个需求写 5 遍代码 → 理解深度远高于单独看书
- 沉淀面试素材：多语言对比、技术选型、优缺点、边界场景
- 沉淀可复用 Demo：直接看到不同语言的写法、并发模型、错误处理、依赖管理、部署差异

---

## 📋 五门语言定位

| 语言 | 类型系统 | 内存管理 | 并发核心范式 | 主打场景 |
|------|---------|---------|-------------|---------|
| **Java** | 静态 OOP | GC | 线程池 + 锁 | 企业级业务系统、生态最全 |
| **Go** | 静态 | GC | Goroutine + Channel | 云原生、基础设施、中间件 |
| **Python** | 动态 | GC | GIL + asyncio | AI、数据分析、脚本、快速原型 |
| **Rust** | 静态 | 无 GC，所有权 | 编译期防竞态 | 高性能中间件、CLI、系统工具 |
| **TS(Node)** | 可选静态 | GC | 事件循环 + Promise | BFF、IO 密集服务、全栈一体 |

### 选型一句话决策

| 场景 | 推荐语言 |
|------|---------|
| 大型企业业务系统、强一致性要求 | **Java** |
| 云原生组件、微服务网关、轻量后端 | **Go** |
| AI 应用、数据处理、快速脚本 | **Python** |
| 高性能中间件、底层工具、安全敏感 | **Rust** |
| BFF 层、前端后端一体化、IO 密集 | **TS(Node)** |

---

## 📂 仓库结构

```
Multi-Lang-Backend-Showcase/
├── README.md                 # 你正在读的文件
├── ROADMAP.md                # 完整迭代计划 + 进度追踪 ⭐
├── VERIFICATION.md           # 18 场景 × 5 语言（90 个验证单元）本地验证报告（缺陷清单 + 验证方法）⭐
├── docker-compose.yml        # 拉起 00-hello-http 的 5 个语言服务（各语言目录已含 Dockerfile）
├── mise.toml                 # mise 统一 SDK 版本声明（当前只管 Java）
├── .gitignore
│
├── .wb_verify/               # 验证工具链（脚本入库，运行结果不入库）
│   ├── verify_all.py         # 统一验证脚本（18 场景 × 5 语言）
│   ├── check_graceful.py     # 场景 12 定点复核（在途请求 / 关闭日志 / 端口释放）
│   ├── clean_probe_files.py  # 清理沙箱遗留的随机名探针文件
│   ├── all_logs/             # 每个「场景 × 语言」的运行日志（由全局 `*.log` 规则忽略）
│   └── runs/                 # 每次运行的结果归档（已忽略）
│
├── docs/                     # 专题深度文档
│   ├── philosophy.md         # 五大语言核心设计哲学总对比
│   ├── concurrency.md        # 并发模型深度专题 ⭐
│   ├── error-handle.md       # 错误处理专题
│   ├── dependency.md         # 依赖管理 & 构建工具专题
│   ├── checklist.md          # Java 开发者踩坑清单（思维定势）
│   ├── observability.md      # 可观测性专题（日志、metrics、trace）
│   └── cloud-native-practice.md  # 云原生工程实践（优雅关闭、信号处理）
│
├── scenarios/                # 核心：业务场景，每个场景 5 套实现
│   ├── 00-hello-http/        # 最小 HTTP 服务（阶段1完成）
│   ├── 01-json-serialize/    # JSON 序列化反序列化
│   ├── 02-concurrent-task/   # 并发任务处理 ⭐⭐
│   ├── 03-cli-tool/          # 命令行工具开发
│   ├── 04-file-io/           # 文件目录读写
│   ├── 05-unit-test-mock/    # 单元测试与 mock
│   ├── 06-simple-rag-demo/   # 轻量 RAG 小 Demo（Agent 亮点）
│   ├── 07-structured-logging/ # 结构化日志
│   ├── 08-config-management/  # 多环境配置
│   ├── 09-http-client/       # HTTP 客户端（超时/重试）
│   ├── 10-rate-limit/        # 单机内存限流
│   ├── 11-db-crud-pool/      # 数据库 CRUD + 连接池
│   ├── 12-graceful-shutdown/ # 优雅关闭
│   │
│   └── ── 边界场景（某些语言天生不擅长，用于突出技术选型）──
│       ├── 13-cpu-bound-parallel/ # CPU 密集并行计算 ⭐
│       ├── 14-data-analysis/     # 数据分析处理（DataFrame 聚合）⭐
│       ├── 15-structured-concurrency/ # 结构化并发 + 取消传播 ⭐
│       ├── 16-large-file-streaming/   # 大文件流式处理（内存上限契约）⭐
│       └── 17-error-handling/         # 错误处理深水区（可观测性契约）⭐
│
└── bench/                    # 压测脚本
    └── http-bench.sh         # wrk/curl 压测脚本
```

### 每个场景目录结构

```
scenarios/XX-scenario-name/
├── java/          # SpringBoot + logback-spring.xml（LogstashEncoder JSON 日志）
├── go/            # gin-gonic/gin + go.uber.org/zap（结构化日志）
├── python/        # FastAPI + structlog（结构化日志）
├── rust/          # axum + tracing/tracing-subscriber（结构化日志）
├── ts-node/       # fastify + pino（结构化日志）
└── README.md      # 本场景横向对比文档（统一模板）
```

> **2026-11-14 全量升级**：所有场景已统一到生产级开源组件 + 结构化日志框架（DEBUG 级别 + JSON stdout）。
> 详情见 [docs/dependency.md](docs/dependency.md) 和 [docs/observability.md](docs/observability.md)。

---

## 🚀 快速上手

### 前置条件

| 语言 | 推荐版本 | SDK 管理器 |
|------|---------|-----------|
| Java | Zulu JDK 17 | mise / sdkman |
| Go | 1.22+（`go.mod` 声明为 1.22） | mise |
| Python | 3.11+ | mise |
| Rust | stable（edition 2021） | rustup |
| Node.js | **24**（见下方说明） | mise / nvm |

> 本项目推荐用 [mise](https://mise.jdx.dev/) 统一管理所有语言 SDK 版本（`mise.toml` 中已声明 Java）。

> ⚠️ **Node 版本务必选 24**：`11-db-crud-pool` 使用的 `better-sqlite3` 是**原生模块**，官方未提供
> Node v24 的预编译产物，需 `npm rebuild better-sqlite3 --build-from-source` 现场编译。
> 构建产物与 Node ABI 绑定，**换用 v22 等其它大版本会重新报 `Could not locate the bindings file`**。

### 运行 00-hello-http

**方式一：容器一键拉起**（无需本地装任何 SDK）

```bash
docker compose up -d --build
curl 'localhost:8080/hello?name=world'   # Java
curl 'localhost:8081/hello?name=world'   # Go
curl 'localhost:8082/hello?name=world'   # Python
curl 'localhost:8083/hello?name=world'   # Rust
curl 'localhost:8084/hello?name=world'   # TS-Node
```

> 只有 `00-hello-http` 提供了 Dockerfile，其余 17 个场景未做容器化。

**方式二：本地直接运行**

```bash
# Python 依赖统一用根目录 .venv（uv 管理），首次使用：
uv sync                       # 从 pyproject.toml 安装所有依赖到根目录 .venv

# Java (端口 8080)
cd scenarios/00-hello-http/java
mvn spring-boot:run

# Go (端口 8081) — 各场景独立 go.mod
cd scenarios/00-hello-http/go
go run main.go

# Python (端口 8082) — 用根目录 .venv
cd scenarios/00-hello-http/python
../../../.venv/bin/python main.py
# 或：uv run python scenarios/00-hello-http/python/main.py

# Rust (端口 8083)
cd scenarios/00-hello-http/rust
cargo run

# TS-Node (端口 8084)
cd scenarios/00-hello-http/ts-node
npm install && npm run dev
```

### 统一 API 契约

```
GET /hello?name={xxx}
→ {"msg": "hello {xxx}"}
→ {"msg": "hello world"}  // name 参数缺省
```

### 压测

```bash
# 安装 wrk（macOS）
brew install wrk

# 一键压测 5 个服务
bash bench/http-bench.sh
```

---

## 📊 对比维度模板

每个场景的 `README.md` 统一使用以下对比表格：

| 维度 | Java | Go | Python | Rust | TS(Node) |
|------|------|----|--------|------|----------|
| 类型系统 | | | | | |
| 依赖 & 构建 | | | | | |
| 并发模型 | | | | | |
| 错误处理 | | | | | |
| 内存 / 启动 | | | | | |
| 优势 | | | | | |
| 痛点 & 坑 | | | | | |

---

## 📅 迭代计划

> **完整的进度追踪见 [ROADMAP.md](ROADMAP.md)**

| 阶段 | 内容 | 状态 |
|------|------|------|
| **Phase 1** | 骨架 + `00-hello-http` + 顶层 README + docs + bench 脚本 | ✅ 已完成 |
| **Phase 2** | `01-json-serialize` / `02-concurrent-task` ⭐⭐ / `03-cli-tool` | ✅ 已完成 |
| **Phase 3** | `04-file-io` / `05-unit-test-mock` / `06-simple-rag-demo`（Agent 亮点） | ✅ 已完成 |
| **Phase 4** | `07-structured-logging` / `08-config-management` / `09-http-client` | ✅ 已完成 |
| **Phase 5** | `10-rate-limit` / `11-db-crud-pool` / `12-graceful-shutdown` | ✅ 已完成 |
| **Phase 6** | 边界场景：`13-cpu-bound-parallel`（CPU 密集）/ `14-data-analysis`（数据分析）/ `15-structured-concurrency`（取消传播）/ `16-large-file-streaming`（流式）/ `17-error-handling`（错误处理） | ✅ 已完成（5/5） |

> **⚠️ 严格按顺序完成，不要追求大而全**。优先保证每个 demo 可运行、文档写到位。
> **🔍 18 个场景 × 5 语言本地验证结果见 [VERIFICATION.md](VERIFICATION.md)**（含沙箱环境限制说明）。

### 前置 13 个场景 vs 边界场景

前 13 个场景的设计前提是「**五门语言都能做**，差异在范式与心智负担」——这保证了对比公平，
但也无法回答「**什么时候某门语言根本不该上场**」。边界场景用来补上这一环：

| 边界场景 | 谁的主场 | 谁需要补救 | 补救代价 |
|---------|---------|-----------|---------|
| `13-cpu-bound-parallel` | Rust / Go / Java | Python（GIL）、TS(Node)（单线程 + 无 64 位整数） | Python 须换 `multiprocessing`（序列化成本）；Node 须 `worker_threads` + `BigInt`（慢一个数量级） |
| `14-data-analysis` | Python(pandas) / Rust(polars) | Java / Go / TS(Node) | 没有一等公民的 DataFrame，聚合与分位数要手写；TS 的 danfojs 已停更三年、依赖 tfjs-node 原生绑定 |
| `15-structured-concurrency` | Go(context) / Python(TaskGroup) | Java / Rust | Java 的 `StructuredTaskScope` 仍是 JDK 21 preview，且**用线程中断代替取消传播**（拿不到取消原因、不可中断处失效）；Rust 无语言级原语，取消要自建广播 + 每个 await 点 select |
| `16-large-file-streaming` | Go / Rust（读进调用方缓冲，天然固定内存） | Python / TS(Node) / Java | 标准库默认语义就是"一次读全"，须退回 `os.read` / `readSync` 自己管缓冲 + 手写行边界；Java 还**拿不到 RSS**（只能 fork `ps`）。一次性读入版实测 RSS 增量是数据的 12 倍 |
| `17-error-handling` | Rust(`Result`) / Java(`@RestControllerAdvice`) | Go / Python / TS(Node) | Go 的 `%w` 漏一个就断链且编译器不提醒、goroutine 错误无钩子；Python 漏 `from` 只剩 `__context__`；TS 的 `cause` 需 ES2022，**Node 默认还会因未捕获 rejection 直接终止进程** |

---

## 🤝 贡献规范

1. 同一个场景，**5 种语言的业务逻辑必须完全对齐**（输入输出一致）
2. 使用**生产级开源组件**，不要手写玩具轮子（见 [docs/dependency.md](docs/dependency.md) 的组件清单）
3. 日志必须接入**结构化日志框架**，最低 DEBUG 级别，JSON 输出到 stdout
4. 每个 demo 必须写清楚**启动步骤**
5. 不做过度封装，demo 追求简洁易懂
6. 禁止大二进制提交到 git

---

## 📝 License

MIT License
