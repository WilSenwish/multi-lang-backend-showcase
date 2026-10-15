# multi-lang-backend-showcase

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
multi-lang-backend-showcase/
├── README.md                 # 你正在读的文件
├── ROADMAP.md                # 完整迭代计划 + 进度追踪 ⭐
├── docker-compose.yml        # 一键拉起全部 demo 服务（阶段2实现）
├── .gitignore
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
│   └── 12-graceful-shutdown/ # 优雅关闭
│
└── bench/                    # 压测脚本
    └── http-bench.sh         # wrk/curl 压测脚本
```

### 每个场景目录结构

```
scenarios/XX-scenario-name/
├── java/          # SpringBoot 可运行项目
├── go/            # main.go + go.mod
├── python/        # FastAPI / asyncio
├── rust/          # axum + Cargo.toml
├── ts-node/       # fastify + package.json
└── README.md      # 本场景横向对比文档（统一模板）
```

---

## 🚀 快速上手

### 前置条件

| 语言 | 推荐版本 | SDK 管理器 |
|------|---------|-----------|
| Java | Zulu JDK 17 | mise / sdkman |
| Go | 1.22+ | mise |
| Python | 3.11+ | mise |
| Rust | stable | rustup |
| Node.js | 20 LTS | mise / nvm |

> 本项目推荐用 [mise](https://mise.jdx.dev/) 统一管理所有语言 SDK 版本。

### 运行 00-hello-http

```bash
# Java (端口 8080)
cd scenarios/00-hello-http/java
mvn spring-boot:run

# Go (端口 8081)
cd scenarios/00-hello-http/go
go run main.go

# Python (端口 8082)
cd scenarios/00-hello-http/python
pip install -r requirements.txt
uvicorn main:app --port 8082

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
| **Phase 2** | `01-json-serialize` / `02-concurrent-task` ⭐⭐ / `03-cli-tool` | 🔲 待开始 |
| **Phase 3** | `04-file-io` / `05-unit-test-mock` / `06-simple-rag-demo`（Agent 亮点） | 🔲 待开始 |
| **Phase 4** | `07-structured-logging` / `08-config-management` / `09-http-client` | 🔲 待开始 |
| **Phase 5** | `10-rate-limit` / `11-db-crud-pool` / `12-graceful-shutdown` | 🔲 待开始 |

> **⚠️ 严格按顺序完成，不要追求大而全**。优先保证每个 demo 可运行、文档写到位。

---

## 🤝 贡献规范

1. 同一个场景，**5 种语言的业务逻辑必须完全对齐**（输入输出一致）
2. 使用社区主流框架，不要手写玩具轮子
3. 每个 demo 必须写清楚**启动步骤**
4. 不做过度封装，demo 追求简洁易懂
5. 禁止大二进制提交到 git

---

## 📝 License

MIT License
