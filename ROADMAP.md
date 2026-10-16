# 🗺️ Roadmap & 进度追踪

> 仓库分 5 个阶段迭代，**严格按顺序完成**，不追求大而全，每个阶段交付可运行、文档完整、可对外 release 的成果。

---

## 阶段总览

| 阶段 | 场景数 | 核心目标 | 状态 |
|------|--------|---------|------|
| **Phase 1** 骨架 + Hello HTTP | 1 | 仓库结构、模板、首个场景跑通 | ✅ 已完成 |
| **Phase 2** 核心场景 | 3 | JSON / 并发 / CLI — 最能体现语言差异 | ✅ 已完成 |
| **Phase 3** 拓展场景 | 3 | 文件 IO / 测试 Mock / RAG Demo（亮点） | ✅ 已完成 |
| **Phase 4** 生产高频场景 | 3 | 结构化日志 / 配置管理 / HTTP 客户端 | ✅ 已完成 |
| **Phase 5** 剩余场景 | 3 | 限流 / DB CRUD / 优雅关闭 | ✅ 已完成 |
| **Phase 6** 边界场景 | 5 | 刻意选"某些语言天生不擅长"的问题，突出**技术选型** | ✅ **已完成**（5/5） |

---

## Phase 1 — ✅ 已完成（骨架 + Hello HTTP）

- [x] 仓库目录结构（scenarios/ / docs/ / bench/）
- [x] 顶层 README（选型矩阵、快速上手、迭代计划）
- [x] docs/ 7 个专题文档（philosophy / concurrency / error-handle / dependency / checklist / observability / cloud-native-practice）
- [x] **00-hello-http** — 5 种语言完整实现 + 对比 README
- [x] bench/http-bench.sh 压测脚本
- [x] docker-compose.yml + 00 场景 5 个语言的 Dockerfile（`docker compose up -d --build` 可一键拉起）
- [x] .gitignore

---

## Phase 2 — ✅ 核心场景（已完成）

| # | 场景 | 主题 | 对比亮点 | 依赖 | 状态 |
|---|------|------|---------|------|------|
| 01 | **json-serialize** | JSON 序列化/反序列化 | 空值处理、类型安全、性能、tag 设计 | 无 | ✅ **已完成** |
| 02 | **concurrent-task** ⭐⭐ | 并发批量任务处理 | **最核心场景** — 五门语言并发模型本质差异 | 无 | ✅ **已完成** |
| 03 | **cli-tool** | 命令行小工具 | 参数解析、退出码、stdout 输出 | 无 | ✅ **已完成** |

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

## Phase 3 — ✅ 拓展场景（已完成）

| # | 场景 | 主题 | 对比亮点 | 依赖 | 状态 |
|---|------|------|---------|------|------|
| 04 | **file-io** | 文件读写 & 目录遍历 | 同步 vs 异步 IO、路径处理、编码 | 无 | ✅ **已完成** |
| 05 | **unit-test-mock** | 单元测试 & Mock | 测试框架、Mock 能力、覆盖率 | 各语言测试框架 | ✅ **已完成** |
| 06 | **simple-rag-demo** 🔥 | 轻量 RAG 问答 | Agent/AI 方向亮点场景 | 可选 LLM API（无 API 走本地 mock） | ✅ **已完成** |

---

## Phase 4 — ✅ 生产高频场景（已完成）

| # | 场景 | 主题 | 对比亮点 | 依赖 | 状态 |
|---|------|------|---------|------|------|
| 07 | **structured-logging** | 结构化日志 + 日志切割 | 性能开销、零分配、云原生适配 | 各语言日志库 | ✅ **已完成** |
| 08 | **config-management** | 多环境配置 + 校验 | 配置校验时机（编译期 vs 运行时） | yaml/env | ✅ **已完成** |
| 09 | **http-client** | HTTP 客户端 + 超时/重试 | 连接池、超时粒度、原生异步 | 各语言 HTTP client | ✅ **已完成** |

---

## Phase 5 — ✅ 全部完成

| # | 场景 | 主题 | 对比亮点 | 依赖 | 状态 |
|---|------|------|---------|------|------|
| 10 | **rate-limit** | 单机内存限流 | 令牌桶/漏桶、并发安全实现 | 无 | ✅ **已完成** |
| 11 | **db-crud-pool** | SQLite CRUD + 连接池 | ORM vs 原生 SQL、Rust sqlx 类型安全 | **SQLite**（零外部依赖） | ✅ **已完成** |
| 12 | **graceful-shutdown** | 优雅关闭（SIGTERM） | 信号捕获、等待机制、K8s 适配 | 无 | ✅ **已完成** |

---

## Phase 6 — ✅ 边界场景（已完成 5/5）

前 13 个场景的设计前提是「**五门语言都能做**，差异在范式与心智负担」——这保证了对比公平，
但回答不了技术选型里最关键的一问：**什么时候某门语言根本不该上场，补救方案又要付出多少代价。**

Phase 6 专门补这一环。每个边界场景都必须写清楚**翻车方的补救方案及其成本** ——
"补救成本"才是选型依据，"不行"只是起点。**刻意不做语言黑帖。**

| # | 场景 | 谁的主场 | 谁需要补救 | 补救代价 | 状态 |
|---|------|---------|-----------|---------|------|
| 13 | **cpu-bound-parallel** | Rust / Go / Java | Python、TS(Node) | Python 须换 `multiprocessing`（进程启动 + pickle 序列化）；Node 须 `worker_threads` + `BigInt`（慢约一个数量级） | ✅ **已完成** |
| 14 | **data-analysis** | Python(pandas) / Rust(polars) | Java / Go / TS | 没有像样的 DataFrame，聚合与分位数要手写；TS 的 danfojs 已停更三年 | ✅ **已完成** |
| 15 | **structured-concurrency** | Go / TS / Python | Java / Rust | Java 的 `StructuredTaskScope` 收尾靠 `Thread.interrupt()` 而非传播取消信号（拿不到取消原因、不可中断处失效，且仍是 preview API）；Rust 无语言级结构化并发，取消要自己搭 | ✅ **已完成** |
| 16 | **large-file-streaming** | Go / Rust | Python / TS(Node) / Java | 标准库默认语义就是"一次读全"，须退回 `os.read` / `readSync` 自己管缓冲 + 手写行边界；Java 还拿不到 RSS（只能 fork `ps`）。一次性读入版实测 RSS 增量达数据的 12 倍 | ✅ **已完成** |
| 17 | **error-handling** | Rust(`Result`) / Java(Advice) | Go / Python / TS(Node) | Go 的 `%w` 漏一个就断链且编译器不提醒、goroutine 错误**完全没有钩子**（panic 还会打挂进程）；Python 漏 `from` 只剩 `__context__`、asyncio task 错误无钩子；TS 的 `cause` 需 ES2022 且 Node 默认会因未捕获 rejection **直接终止进程**。Rust 的 `JoinHandle` 被 drop 时错误静默消失 | ✅ **已完成** |

> 边界场景的**新验收要求**：必须做**契约级断言**（响应内容逐字段与独立 oracle 比对），
> 不能停留在"端口监听级"。判定强度分层见 [VERIFICATION.md](VERIFICATION.md) §10。

| # | 场景 | 主题 | 对比亮点 | 依赖 | 状态 |
|---|------|------|---------|------|------|
| 13 | **cpu-bound-parallel** | CPU 密集并行计算 | GIL / 单线程事件循环 / 无 64 位整数 | 无 | ✅ **已完成** |
| 14 | **data-analysis** | 数据分析处理（20 万行分组聚合，可调至 200 万） | DataFrame 生态差异 | pandas / polars / tablesaw / gonum / danfojs | ✅ **已完成** |
| 15 | **structured-concurrency** | 结构化并发 + 取消传播 | context / AbortController / TaskGroup / cancel 语义 | Java 侧需 JDK 21（preview API） | ✅ **已完成** |
| 16 | **large-file-streaming** | 大文件流式处理（32MB 数据 / 16MiB RSS 增量上限） | 谁会全量读入、行边界怎么拼、RSS 怎么观测 | 无（Go/Rust/Java 全用标准库） | ✅ **已完成** |
| 17 | **error-handling** | 错误处理深水区（五形态 + 异步错误可观测性） | `Result` vs 异常 vs `if err != nil`、错误链、trace 透传 | 无（Rust 用 anyhow） | ✅ **已完成** |

---

## 不做什么（范围边界）

| ❌ 排除 | 原因 |
|---------|------|
| 分布式锁 / 分布式事务 | 太重，依赖多，偏离语言对比 |
| 复杂网关 / 服务注册发现 | 组件太多 |
| JWT / 密码加密 | 偏向密码学工具，语言差异不大 |
| C / C++ / Ruby / PHP / Scala / Haskell | 重复范式或受众小 |
| 一次性实现全部 13 个场景 | 容易烂尾（故拆成 5 个阶段推进） |

---

## 完成一个场景的 Definition of Done

每个场景必须满足：
- [ ] 5 种语言实现全部完成，业务逻辑完全对齐
- [ ] 启动命令可本地直接运行（场景 11 用 SQLite，无需外部数据库）
- [ ] README.md 对比文档完整填写（对比表 + 选型思考）
- [ ] 本机跑通 `.wb_verify/verify_all.py <场景号>`，该场景 × 5 语言全绿
- [ ] **边界场景（Phase 6）额外要求**：验证器必须做**契约级断言**（响应逐字段与独立 oracle 比对），
      不接受只验到"端口监听"
- [ ] 至少 wrk 压测通过（HTTP 类场景）
- [ ] 没有大二进制提交（通过 .gitignore 保证）

---

## 下一步

> **所有 5 个阶段、18 个场景（13 基础 + 5 边界）、5 种语言的实现均已完成，并通过本机验证（当前 90/90 全绿）。**
> 验证方法、缺陷清单与踩坑记录详见 [VERIFICATION.md](VERIFICATION.md)。

已完成的验证轮次：

| 轮次 | 重点 | 结果 |
|------|------|------|
| 第一轮 | 逐个场景跑通（编译期 / 启动期硬错误） | 修复 34 条；清理 49 个探针垃圾文件与 1 个编译产物 |
| 第二轮 | 把判定从"能启动"收紧到"行为正确" | 新发现并修复 5 条静默缺陷；修掉验证器 1 处**假阳性**判定 |
| 第三轮 | 仓库更名后从新路径全量复跑 | 65/65 全绿；验证脚本路径改为由 `__file__` 推导，不再写死绝对路径 |

后续可选项：

1. **验证强度加强计划（进行中，只 commit 不推远端）** —— 把 00~12 从"端口监听级"逐批升级到契约级，
   每批一个提交，批次划分与进度见 [VERIFICATION.md §12](VERIFICATION.md)。
   已完成批次 1（`00-hello-http` + `01-json-serialize`，10/10 全绿；顺带修掉 5 处跨语言偏差）。
   已完成批次 2（`02-concurrent-task` + `04-file-io`，10/10 全绿；修掉 12 处跨语言偏差，
   含 02 的 Java camelCase 静默不一致与 04 的一个从未被触发的 Java NPE）。
   下一批：`06-simple-rag-demo` + `07-structured-logging`。
2. ~~**继续 Phase 6 剩余 1 个边界场景**（`17-error-handling`）。~~ ✅ 已完成（Phase 6 五个边界场景全部交付）
3. 补充压测数据（`bench/http-bench.sh`）。
4. 扩展 docs 专题深度（可参考本轮沉淀的 Python/uvicorn 优雅关闭踩坑，已写入 `docs/cloud-native-practice.md`）。
