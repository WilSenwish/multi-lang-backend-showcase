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
| **Phase 6** 边界场景 | 5 | 刻意选"某些语言天生不擅长"的问题，突出**技术选型** | 🚧 进行中（1/5） |

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

## Phase 6 — 🚧 边界场景（进行中）

前 13 个场景的设计前提是「**五门语言都能做**，差异在范式与心智负担」——这保证了对比公平，
但回答不了技术选型里最关键的一问：**什么时候某门语言根本不该上场，补救方案又要付出多少代价。**

Phase 6 专门补这一环。每个边界场景都必须写清楚**翻车方的补救方案及其成本** ——
"补救成本"才是选型依据，"不行"只是起点。**刻意不做语言黑帖。**

| # | 场景 | 谁的主场 | 谁需要补救 | 补救代价 | 状态 |
|---|------|---------|-----------|---------|------|
| 13 | **cpu-bound-parallel** | Rust / Go / Java | Python、TS(Node) | Python 须换 `multiprocessing`（进程启动 + pickle 序列化）；Node 须 `worker_threads` + `BigInt`（慢约一个数量级） | ✅ **已完成** |
| 14 | **data-analysis** | Python(pandas) / Rust(polars) | Java / Go / TS | 没有像样的 DataFrame，聚合与分位数要手写 | ⬜ 待开始 |
| 15 | **structured-concurrency** | Go / TS | Java | 取消传播语义弱；JDK 21 虚拟线程可以改善（本场景 Java 单独使用 JDK 21） | ⬜ 待开始 |
| 16 | **large-file-streaming** | Go / Rust | Java | 内存约束下易 OOM，须刻意流式 | ⬜ 待开始 |
| 17 | **error-handling** | Rust / Go | Python / TS | 无编译期错误类型约束，错误链靠约定 | ⬜ 待开始 |

> 边界场景的**新验收要求**：必须做**契约级断言**（响应内容逐字段与独立 oracle 比对），
> 不能停留在"端口监听级"。判定强度分层见 [VERIFICATION.md](VERIFICATION.md) §10。

| # | 场景 | 主题 | 对比亮点 | 依赖 | 状态 |
|---|------|------|---------|------|------|
| 13 | **cpu-bound-parallel** | CPU 密集并行计算 | GIL / 单线程事件循环 / 无 64 位整数 | 无 | ✅ **已完成** |
| 14 | **data-analysis** | 数据分析处理（100 万行聚合） | DataFrame 生态差异 | pandas / polars / tablesaw / gonum / danfojs | ⬜ 待开始 |
| 15 | **structured-concurrency** | 结构化并发 + 取消传播 | context / AbortController / TaskGroup / cancel 语义 | 无 | ⬜ 待开始 |
| 16 | **large-file-streaming** | 大文件流式处理（1GB + 64MB 内存上限） | 迭代器统一程度、谁会全量读入 | 无 | ⬜ 待开始 |
| 17 | **error-handling** | 错误处理深水区 | Result vs 异常 vs `if err != nil`、错误链 | 无 | ⬜ 待开始 |

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

> **所有 5 个阶段、13 个场景、5 种语言的实现均已完成，并通过三轮本机验证（当前 65/65 全绿）。**
> 验证方法、缺陷清单与踩坑记录详见 [VERIFICATION.md](VERIFICATION.md)。

已完成的验证轮次：

| 轮次 | 重点 | 结果 |
|------|------|------|
| 第一轮 | 逐个场景跑通（编译期 / 启动期硬错误） | 修复 34 条；清理 49 个探针垃圾文件与 1 个编译产物 |
| 第二轮 | 把判定从"能启动"收紧到"行为正确" | 新发现并修复 5 条静默缺陷；修掉验证器 1 处**假阳性**判定 |
| 第三轮 | 仓库更名后从新路径全量复跑 | 65/65 全绿；验证脚本路径改为由 `__file__` 推导，不再写死绝对路径 |

后续可选项：

1. **给已有 `http` 类场景补契约级断言** —— 做法已在场景 13 上验证（§10）：用独立 oracle 逐字段比对。
   优先补 `02-concurrent-task`，它已确认存在 Java camelCase 与其余语言 snake_case 的**静默不一致**（VERIFICATION.md §11）。
2. **继续 Phase 6 剩余 4 个边界场景**（14~17）。
3. 补充压测数据（`bench/http-bench.sh`）。
4. 扩展 docs 专题深度（可参考本轮沉淀的 Python/uvicorn 优雅关闭踩坑，已写入 `docs/cloud-native-practice.md`）。
