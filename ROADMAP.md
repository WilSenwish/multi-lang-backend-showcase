# 🗺️ Roadmap & 进度追踪

> 仓库分 5 个阶段迭代，**严格按顺序完成**，不追求大而全，每个阶段交付可运行、文档完整、可对外 release 的成果。

---

## 阶段总览

| 阶段 | 场景数 | 核心目标 | 状态 |
|------|--------|---------|------|
| **Phase 1** 骨架 + Hello HTTP | 1 | 仓库结构、模板、首个场景跑通 | ✅ 已完成 |
| **Phase 2** 核心场景 | 3 | JSON / 并发 / CLI — 最能体现语言差异 | 🔲 待开始 |
| **Phase 3** 拓展场景 | 3 | 文件 IO / 测试 Mock / RAG Demo（亮点） | 🔲 待开始 |
| **Phase 4** 生产高频场景 | 3 | 结构化日志 / 配置管理 / HTTP 客户端 | 🔲 待开始 |
| **Phase 5** 剩余场景 | 2 | 限流 / DB CRUD / 优雅关闭 | 🔲 待开始 |

---

## Phase 1 — ✅ 已完成（骨架 + Hello HTTP）

- [x] 仓库目录结构（scenarios/ / docs/ / bench/）
- [x] 顶层 README（选型矩阵、快速上手、迭代计划）
- [x] docs/ 5 个专题文档大纲
- [x] **00-hello-http** — 5 种语言完整实现 + 对比 README
- [x] bench/http-bench.sh 压测脚本
- [x] docker-compose.yml 占位
- [x] .gitignore

---

## Phase 2 — � 核心场景（进行中）

| # | 场景 | 主题 | 对比亮点 | 依赖 | 状态 |
|---|------|------|---------|------|------|
| 01 | **json-serialize** | JSON 序列化/反序列化 | 空值处理、类型安全、性能、tag 设计 | 无 | 🔲 |
| 02 | **concurrent-task** ⭐⭐ | 并发批量任务处理 | **最核心场景** — 五门语言并发模型本质差异 | 无 | ✅ **已完成** |
| 03 | **cli-tool** | 命令行小工具 | 参数解析、退出码、stdout 输出 | 无 | 🔲 |

### 01 json-serialize 需求预览
- 统一输入一个嵌套 JSON 对象
- 序列化为 JSON 字符串
- 反序列化为强类型对象
- 测试：null 值、空集合、默认值、嵌套对象

### 02 concurrent-task 需求预览（⭐重中之重）
- 统一需求：并发处理 100 个任务（模拟：HTTP 请求 / 计算 / 文件处理）
- 对比：吞吐量、延迟、资源占用、代码复杂度
- Java: ThreadPoolExecutor + CompletableFuture
- Go: goroutine + channel + WaitGroup
- Python: asyncio + asyncio.gather（GIL 限制对比）
- Rust: tokio 多线程 + JoinHandle
- TS(Node): Promise.all + async-await（事件循环）

### 03 cli-tool 需求预览
- 简单 wc（word count）：统计文件行数、词数、字符数
- 支持 `-l` 只统计行、`-w` 只统计词、`-c` 只统计字符
- 支持 `-f <file>` 或 stdin 输入

---

## Phase 3 — 🔲 拓展场景

| # | 场景 | 主题 | 对比亮点 | 依赖 | 状态 |
|---|------|------|---------|------|------|
| 04 | **file-io** | 文件读写 & 目录遍历 | 同步 vs 异步 IO、路径处理、编码 | 无 | 🔲 |
| 05 | **unit-test-mock** | 单元测试 & Mock | 测试框架、Mock 能力、覆盖率 | 各语言测试框架 | 🔲 |
| 06 | **simple-rag-demo** | 轻量 RAG 问答 | Agent/AI 方向亮点场景 | OpenAI 兼容 API | 🔲 |

---

## Phase 4 — 🔲 生产高频场景

| # | 场景 | 主题 | 对比亮点 | 依赖 | 状态 |
|---|------|------|---------|------|------|
| 07 | **structured-logging** | 结构化日志 + 日志切割 | 性能开销、零分配、云原生适配 | 各语言日志库 | 🔲 |
| 08 | **config-management** | 多环境配置 + 校验 | 配置校验时机（编译期 vs 运行时） | yaml/env | 🔲 |
| 09 | **http-client** | HTTP 客户端 + 超时/重试 | 连接池、超时粒度、原生异步 | 各语言 HTTP client | 🔲 |

---

## Phase 5 — 🔲 剩余场景

| # | 场景 | 主题 | 对比亮点 | 依赖 | 状态 |
|---|------|------|---------|------|------|
| 10 | **rate-limit** | 单机内存限流 | 令牌桶/漏桶、并发安全实现 | 无 | 🔲 |
| 11 | **db-crud-pool** | MySQL CRUD + 连接池 | ORM vs 原生 SQL、Rust sqlx 编译期校验 | **MySQL** | 🔲 |
| 12 | **graceful-shutdown** | 优雅关闭（SIGTERM） | 信号捕获、等待机制、K8s 适配 | 无 | 🔲 |

---

## 不做什么（范围边界）

| ❌ 排除 | 原因 |
|---------|------|
| 分布式锁 / 分布式事务 | 太重，依赖多，偏离语言对比 |
| 复杂网关 / 服务注册发现 | 组件太多 |
| JWT / 密码加密 | 偏向密码学工具，语言差异不大 |
| C / C++ / Ruby / PHP / Scala / Haskell | 重复范式或受众小 |
| 一次性实现全部 12 个场景 | 容易烂尾 |

---

## 完成一个场景的 Definition of Done

每个场景必须满足：
- [ ] 5 种语言实现全部完成，业务逻辑完全对齐
- [ ] 启动命令可本地直接运行（除 Phase 5 的 DB 场景）
- [ ] README.md 对比文档完整填写（对比表 + 选型思考）
- [ ] 至少 wrk 压测通过（HTTP 类场景）
- [ ] 没有大二进制提交（通过 .gitignore 保证）

---

## 下一步

> **当前建议：进入 Phase 2，优先完成 02-concurrent-task**。并发模型是 Java 开发者最关心、五门语言差异最大的场景。
