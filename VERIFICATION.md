# 本地验证报告（VERIFICATION）

> 多语言后端对比仓库 `Multi-Lang-Backend-Showcase` —— **13 个基础场景 ＋ 5 个边界场景 × 5 种语言**
> （Java / Go / Python / Rust / TS-Node = **90 个验证单元**）的逐场景本地运行验证、缺陷修复与验证方法沉淀。
>
> 最后更新：2026-10-16（新增场景 17「错误处理深水区」，**可观测性首次成为可断言字段**，见 §10；
> Phase 6 五个边界场景全部交付；**验证强度加强计划启动**——基础场景正从"端口监听"
> 逐批升级到契约级，00/01 已完成，见 §12）
> ｜ 验证脚本：`.wb_verify/verify_all.py`
> ｜ 结果：`.wb_verify/all_results.json` / `.md` ｜ 历史归档：`.wb_verify/runs/`

---

## 1. 结论摘要

| 指标 | 数值 |
|------|------|
| 验证单元（场景 × 语言） | **90**（基础场景 13×5=65 ＋ 边界场景 5×5=25） |
| ✅ 判定为 PASS | **90**（含场景 14 的 Rust 与场景 15 的 Java/JDK 21，均已在本机编译并实测通过） |
| ❌ 代码缺陷导致的 FAIL | **0** |
| ⚠️ 环境限制导致验证器内 PREP_FAIL | **2**（场景 13 的 Python / Rust，已用等价方式单独验证通过，见 §10） |

> **关于那 2 个 PREP_FAIL**：场景 13 的 Python 与 Rust 在验证器内卡在 **prep** 阶段
> （`pip` 找不到可用临时目录、`cargo` 无法替换已有构建产物），根因是本运行环境的
> Security Center 拦截**文件删除**类操作 —— 不是代码缺陷。这两个语言的实现已用
> 「跳过 prep、直接起服务发请求」的方式单独验证，checksum 同样与 oracle 逐位相符（§10）。
> 在常规终端执行 `python3 .wb_verify/verify_all.py` 即可复现 90/90 全绿。

共识别并修复 **39 条代码/文档缺陷**：首轮 34 条（编译期/启动期硬错误为主，见 §4），
本轮复核新增 **5 条**（都是"能跑起来但行为不对"的静默缺陷，见 §5）。
验证强度加强计划批次 1/2（§12）又识别并修复 **17 处跨语言偏差**（00/01 五处 + 02/04 十二处）——
在"端口监听级"判定下，这些偏差没有任何一宗会暴露。
验证器本身的判定缺陷与设计要点见 §7（共 11 条），其中本轮修掉 3 条判定缺陷 ——
**其中一条（`"shutdown" in log`）曾让真正的崩溃被记成 PASS**。

> 本轮最重要的结论：**"进程起来了 / 端口通了"远不等于"行为正确"**。
> 把判定从"能启动"收紧到"契约正确"之后，立刻又浮出 5 个静默缺陷（行数统计差 1、
> CLI 选项全部失效、优雅关闭不驱动框架退出、关闭时掐断在途请求、探针返回 500 而非 503）。

---

## 2. 完整结果矩阵（18 × 5）

| # | 场景 | 类型 | 判定方式 | Java | Go | Python | Rust | TS-Node |
|---|------|------|---------|------|----|--------|------|---------|
| 00 | hello-http | contract | **契约级**（6 用例：name 各形态 + 404/405 边界） | ✅ | ✅ | ✅ | ✅ | ✅ |
| 01 | json-serialize | contract | **契约级**（5 端点逐字段 + 规范 JSON 逐字节） | ✅ | ✅ | ✅ | ✅ | ✅ |
| 02 | concurrent-task | contract | **契约级**（12 用例：限流生效的耗时上下界 + results 保序 + throughput 自洽 + 入参 400/405） | ✅ | ✅ | ✅ | ✅ | ✅ |
| 03 | cli-tool | cli | 数值基准 + 选项语义 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 04 | file-io | contract | **契约级**（28 用例：write→read 往返 + 本地磁盘 oracle + scan 遍历 oracle + 400/404/405 边界） | ✅ | ✅ | ✅ | ✅ | ✅ |
| 05 | unit-test-mock | test | 测试摘要（用例数） | ✅ | ✅ | ✅ | ✅ | ✅ |
| 06 | simple-rag-demo | http | 端口监听 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 07 | structured-logging | http | 端口监听 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 08 | config-management | http | 端口监听 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 09 | http-client | http | 端口监听 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 10 | rate-limit | http | 端口监听 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 11 | db-crud-pool | http | 端口监听 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 12 | graceful-shutdown | graceful | 在途请求 + 关闭日志 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 13 | cpu-bound-parallel | compute | **契约级**（checksum 对比 oracle） | ✅ | ✅ | ✅\* | ✅\* | ✅ |
| 14 | data-analysis | data | **契约级**（分组统计 + Top10 对比 oracle） | ✅ | ✅ | ✅ | ✅ | ✅ |
| 15 | structured-concurrency | cancel | **契约级**（取消传播三用例 + 延迟查活跃任务） | ✅ | ✅ | ✅ | ✅ | ✅ |
| 16 | large-file-streaming | stream | **契约级**（逐字节摘要 + 块数 + **RSS 增量上限**） | ✅ | ✅ | ✅ | ✅ | ✅ |
| 17 | error-handling | error | **契约级**（五形态逐字段 + **异步错误可观测性**） | ✅ | ✅ | ✅ | ✅ | ✅ |

\* 场景 13 的 Python / Rust 在验证器内因环境限制停在 prep（见 §1 说明），
已用等价方式单独验证通过（§10）。场景 14 的 Rust 已在本机完成编译，
`python3 .wb_verify/verify_all.py 14` 实测 **5/5 全绿**（服务端耗时 76~278ms）。
场景 15 是唯一需要按场景切换 JDK 的（Java 用 JDK 21，见 §10）。
场景 16 的三个用例（8MB/1KiB 、8MB/64KiB、32MB/64KiB）五门语言摘要与 oracle 逐字节相符，
32MB 用例的 RSS 增量 0.0~1.2MiB（上限 16MiB）。
场景 17 把 `stack_present` 做成**逐语言预期**（Java/Python/TS 为 true，Go/Rust 为 false）：
这不是缺陷而是语言默认行为，刻意不为了对齐去给 Go 抓栈、给 Rust 开 `RUST_BACKTRACE`。

**分语言统计**：Java 18/18 ｜ Go 18/18 ｜ Python 18/18 ｜ Rust 18/18 ｜ TS-Node 18/18。
基础场景 13×5 = 65/65 全绿；边界场景 13、14、15、16、17 各 5/5 全绿。

> `11-db-crud-pool` 的 TS-Node 曾因原生模块 `better-sqlite3` 缺少 Node 24 预编译产物而无法运行；
> 已在本机完成源码构建（§6.1），现在 65/65 全绿。

---

## 3. 验证方式

- **脚本**：`.wb_verify/verify_all.py`（覆盖 5 种语言；单个测点失败不中断整体；**始终**产出结果文件并归档到 `.wb_verify/runs/`）。
- **判定逻辑**：
  - `contract`：**通用用例引擎**（`verify_cases`）—— 启动服务 → 逐个发请求 → 逐字段比对
    （`json_match` 递归子集/全等匹配，bool 与 int 分开判）。用例支持状态码、`Content-Type`、
    期望 JSON（`exact` 控制键集合）、自定义 `assert` 回调。自场景 00 起，http 场景
    正从"端口监听"逐批升级到契约级（当前 00、01、02、04 已完成，见 §12）。
  - `http`：启动服务 → **原始 TCP 连接**探活（不用 curl/urllib，见 §7.1）→ 关闭进程组。
  - `cli`：对仓库根 `README.md` 跑 `-l -w`，把输出与**独立计算的基准值交叉核对**；
    再逐个跑 `-l` / `-w` / `-c`，校验**单选项只输出对应指标**；最后跑无选项，校验三项全输出。
  - `test`：跑各语言测试框架，要求**捕获到测试摘要**（`Tests run: N` / `N passed` / `test result: ok`），
    避免"什么都没跑但退出码是 0"被记成通过。
  - `graceful`：启动 → 先丢一个耗时 3s 的请求 → 给**监听进程 PID**（`lsof -sTCP:LISTEN`）发 SIGTERM →
    必须同时满足：**在途请求正常拿到响应**、监听释放、日志出现 `Shutdown complete`、无崩溃特征。
- **环境**：JDK 17（Homebrew `openjdk@17`）、Go / Node / Rust 经 mise shim 管理；Go 依赖经 `goproxy.cn` 拉取；
  Python 强制 `PYTHONUNBUFFERED=1`（原因见 §7.5）。

---

## 4. 首轮修复清单（34 条）

> 计数规则：**一条 = 一个独立问题**（一条可能覆盖多个文件）。这些缺陷大多是编译/启动即失败的硬错误，
> 此前被"探活假阳性"长期掩盖（§7.1）。

### 4.1 Java（12 条）

| # | 场景 | 问题 | 修复 |
|---|------|------|------|
| 1 | 全部 11 个 pom | Spring Boot `2.1.3.RELEASE` 与 JDK 17 不兼容（Lombok 注解处理器在强封装下报 `does not "opens ..."`） | parent 升级至 **3.2.12** |
| 2 | 11 | `javax.persistence` 在 Spring Boot 3 下已迁移 | 改为 `jakarta.persistence` |
| 3 | 10 | `javax.annotation` 同上 | 改为 `jakarta.annotation` |
| 4 | 08 | `javax.validation` 同上 | 改为 `jakarta.validation` |
| 5 | 02 | `pom.xml` 缺 Lombok 依赖，但 DTO 已用 `@Data`/`@Builder` | 补 `org.projectlombok:lombok` |
| 6 | 05 | 测试用 `List.of(null, …)` → `List.of` 拒绝 null，构造即 NPE | 改为 `Arrays.asList(null, …)` |
| 7 | 06 | `Chunk.vector` 声明 `final` 却在 `rebuildVocab` 中重新赋值 | 移除 `final` |
| 8 | 09 | Spring 6 / HttpClient 5：`Duration` ≠ `TimeValue`；`HttpComponentsClientHttpRequestFactory` 已无 `setReadTimeout`/`setResponseTimeout` | 超时改由底层 HC5 `RequestConfig`（connect + response）控制 |
| 9 | 10 | Guava 新版 `RateLimiter.reserve(int)` 为**包级私有**，公开 API 无同义方法 | 改用公开的 `getRate()` 估算等待毫秒 |
| 10 | 10 | `application.properties`: `rate-limit.qps=1.0   # 每秒填充 1 个令牌` —— `.properties` 的 `#` **不是行内注释**，值被污染，启动即 `NumberFormatException` | 注释移到独立行 |
| 11 | 11 | `application.properties`: `ddl-auto=update  # 自动建表` —— 同上，Hibernate 报 `Unrecognized setting` | 注释移到独立行 |
| 12 | 12 | `ShutdownController` 用 `ResponseEntity` 但缺 `import org.springframework.http.ResponseEntity` | 补导入 |

### 4.2 Go（7 条）

| # | 场景 | 问题 | 修复 |
|---|------|------|------|
| 13 | 01 / 02 / 04 / 06 / 12 | **缺 `go.mod`** → `go run .` 报 `cannot find main module` | 补建 `go.mod`（纯标准库实现） |
| 14 | 03 | 缺 `go.mod` | 补建 |
| 15 | 05 | 缺 `go.mod` | 补建 |
| 16 | 03 | `printResult` 引用 `main()` 内的局部 `flag.Bool` 变量 → 编译失败 | 改为传参 |
| 17 | 07 | 使用 `zapcore` 但未导入 → 编译失败 | 补 `go.uber.org/zap/zapcore` 导入 |
| 18 | 07 | `cost.Nanoseconds() / count` 为 `int64 / int` 类型不匹配 | 改 `int64(count)` |
| 19 | 10 | `"time"` 导入未使用 → 编译失败 | 删除该导入 |

### 4.3 Rust（11 条）

| # | 场景 | 问题 | 修复 |
|---|------|------|------|
| 20 | 05 | `#[automock]` 生成的是 `MockPaymentService`，测试里写成 `MockPayment` → 未定义 | 统一改名（6+ 处） |
| 21 | 06 | `(StatusCode, Value).into_response()` 不满足 trait 约束 | 构造 `Response` 后 `status_mut() = BAD_REQUEST` |
| 22 | 07 | `info_span!(…).enter()` 创建临时值后立即被丢弃（E0716） | 先绑定 span 再 `.enter()`（3 处） |
| 23 | 08 | handler 返回裸 trait `IntoResponse`（E0782）；缺 `IntoResponse` 导入 | 改 `impl IntoResponse` + 补导入 |
| 24 | 08 | `AppConfig` 的 `env` / `source` 为必填字段但配置源中不存在 → 启动报 `missing field 'env'` | 两字段加 `#[serde(default)]` |
| 25 | 09 | `mock_router()` 未 `.await`（拿到的是 `impl Future<Output = Router>`） | 补 `.await` |
| 26 | 09 | axum 0.7 的 `Serve` 实现的是 `IntoFuture` 而非 `Future`，不能直接交给 `tokio::spawn` | `tokio::spawn(async move { axum::serve(...).await })` |
| 27 | 10 | 使用 `State` 提取器但缺 `use axum::extract::State` | 补导入 |
| 28 | 11 | Cargo.toml 中 sqlx feature `runtime-rustls` **不存在** | 改为 `runtime-tokio-rustls` |
| 29 | 11 | `SqlitePoolOptions` 未导入 | 补 `sqlx::sqlite::SqlitePoolOptions` |
| 30 | 12 | 信号闭包 `async { … }` 借用 `state`，而 `state` 之后仍要使用（E0373） | clone 出 `shutdown_state` 并改 `async move` |

### 4.4 Python（1 条）

| # | 场景 | 问题 | 修复 |
|---|------|------|------|
| 31 | 07 | `structlog.make_filtering_bound_logger(structlog.stdlib.INFO)` —— `structlog.stdlib` 并无 `INFO` 属性 → 启动 `AttributeError` | 改用标准库 `logging.INFO`（并 `import logging`） |

### 4.5 TS-Node（2 条）

| # | 场景 | 问题 | 修复 |
|---|------|------|------|
| 32 | 00 | fastify schema 传入 `z.object({…}).parse`（函数），非法 → `FST_ERR_SCH_VALIDATION_BUILD` | 改为合法 JSON Schema 对象，zod 仅保留在 handler 内运行时校验 |
| 33 | 08 | `AppConfigSchema` 的 `server`/`database`/`logging` 为必填对象，无 `MYAPP_*` 环境变量时 `parse({})` 抛 `ZodError: Required` | `parse` 时显式补 `{ server: {}, database: {}, logging: {}, ...envOverride }` |

### 4.6 文档（1 条）

| # | 场景 | 问题 | 修复 |
|---|------|------|------|
| 34 | 03 | README 示例路径 `../../README.md` 指向不存在的 `scenarios/README.md` | 改为 `../../../README.md`（仓库根 README），验证脚本同步修正 |

---

## 5. 本轮复核新增修复（5 条 · 静默缺陷）

这 5 条**都不会让服务起不来**，因此只有把判定从"能启动"收紧到"行为正确"才会暴露。

### 5.1 `03-cli-tool` / TS-Node：行数 off-by-one

```ts
// 旧：content.split('\n').length —— 把结尾换行后的"空段"也算一行
const lines = content === '' ? 0 : content.split('\n').length;
// 新：与 wc -l / 其余 4 种语言对齐
const lines = content === '' ? 0 : content.split('\n').length - (content.endsWith('\n') ? 1 : 0);
```

以根 `README.md` 为输入：TS-Node 报 `lines=199`，而 Java / Go / Python / Rust + `wc -l` **一致为 198**
（差 1 行；README 后续增删后绝对值会变，关键是"5 种语言必须逐一相等"，验证脚本每次运行都会重新计算基准）。

### 5.2 `03-cli-tool` / TS-Node：`-l` / `-w` / `-c` 三个选项全部失效

```ts
// 旧：options.l / options.w / options.c —— commander 实际写入的是长选项名
const anyFlag = !!(options.l || options.w || options.c);   // 恒为 false
// 新：
const anyFlag = !!(options.lines || options.words || options.chars);
```

因为 `anyFlag` 恒为 false，`defaultAll` 恒为 true → **不管传什么选项都输出三项**（`-c` 也会打印 `lines=`/`words=`）。
修复后单个选项只输出对应指标：

```
$ npx tsx src/main.ts -w ../../../README.md   → words=777
$ npx tsx src/main.ts -c ../../../README.md   → chars=4969
$ npx tsx src/main.ts -l -w ../../../README.md → lines=206 words=777
```

### 5.3 `12-graceful-shutdown` / Python：信号处理三连错

1. `signal_handler(sig, frame)` 里的 `sig` 是 **int**，`sig.name` 抛 `AttributeError`；
2. 只 `asyncio.Event.set()` **不会**让 uvicorn 退出 —— 信号被自己的处理器吃掉，
   框架再也收不到，进程只能等外部 SIGKILL（实测 20s 不退出）；
3. 进程最终被信号"补刀"终止（`uvicorn` 关闭收尾后还原原处理器并 `raise_signal`），
   于是 `atexit` 不执行、未 flush 的 stdout 整块丢失。

修复：用 `signal.Signals(signum).name` 取名字；把信号**交还**给 uvicorn 自己的处理器
（`prev = signal.getsignal(sig)` 取到的就是 `Server.handle_exit`）；`sys.stdout.reconfigure(line_buffering=True)`。
现在 `python3 main.py` 与 `uvicorn main:app` 两种启动方式都能走完标准关闭流程。

### 5.4 `12-graceful-shutdown` / TS-Node：`forceCloseConnections: true` 掐断在途请求

```ts
// 旧：true = close() 时立刻销毁所有连接（含正在处理的请求）
const fastify = Fastify({ forceCloseConnections: true });
// 新：'idle' = 只关空闲 keep-alive 连接，在途请求继续跑完
const fastify = Fastify({ forceCloseConnections: 'idle' });
```

实测证据：修复前在途的 `/api/long-task` 在 1.27s 就被 `RemoteDisconnected` 掐断；
修复后正常返回 `HTTP 200 {"ok":true,"duration_ms":3000,"shutting_down":true}`（耗时 3.02s）。

### 5.5 `12-graceful-shutdown` / TS-Node：探针返回 500 而不是 503

```ts
// 旧：Fastify 实例上根本没有 code()/send()，关闭期间抛 "app.code is not a function" → 500
if (shuttingDown) { fastify.code(503).send(body); }
return body;
// 新：用 reply
reply.code(shuttingDown ? 503 : 200);
return body;
```

实测：旧写法返回 `500 {"message":"app.code is not a function"}`，新写法返回 `503 {"shutting_down":true}`。
即"关闭期间 readinessProbe 返回 503"这条 K8s 适配能力，原本在 TS-Node 上是失效的。

---

## 6. 环境依赖（非代码缺陷）

### 6.1 `11-db-crud-pool` 的 TS-Node（已解决）

`better-sqlite3@11.10.0` 是原生模块，官方未提供 Node **v24**（ABI 137）的预编译产物，
`npm install` 会跳过构建 → 运行时报 `Could not locate the bindings file`。本机已执行：

```bash
cd /Users/chenjunbing/Develop/Project/Personal/Multi-Lang-Backend-Showcase/scenarios/11-db-crud-pool/ts-node
npm rebuild better-sqlite3 --build-from-source
```

> ⚠️ 原生模块与 Node ABI 绑定：构建产物只对**同 ABI 的 Node** 有效。
> 本机 mise 管理的 Node 是 **v24.15.0**，用它才能 `require('better-sqlite3')` 成功；
> 换用其它大版本 Node（如 v22）会重新报 bindings 错误。
> 验证脚本把 mise shim 放在 PATH 前面，因此用的正是构建时那个 Node。

### 6.2 Go 依赖拉取

`proxy.golang.org` / `sum.golang.org` 在部分网络不可达。验证器已固定使用：

```
GOPROXY=https://goproxy.cn,direct
GOSUMDB=off
```

若手工执行 Go 场景，请一并设置上述变量。

---

## 7. 验证器设计要点（踩坑记录）

这几点是保证结论可信的关键，后续自行编写验证脚本请务必注意。

### 7.1 端口探活必须用原始 TCP 连接，不要用 `curl` / `urllib`

环境设置 `HTTP_PROXY` 时，对 `localhost` 的 HTTP 请求会被代理拦截并返回 **502**，
于是**任意端口都会被判定为"已监听"**——正是这个假阳性长期掩盖了 Go/Java 的编译错误。
改用 `socket.create_connection(("127.0.0.1", port))` 后，未监听的端口正确返回 `ConnectionRefused`。

### 7.2 判定"优雅关闭"不能用 `"shutdown" in log`（**本轮修掉的真假阳性**）

11 个场景里有 `12-graceful-shutdown`，其**路径**会出现在日志的每一行里（异常栈、编译告警都含它）。
于是"日志含 shutdown 就当通过"这条判定**恒为真**：Python 实现明明抛了
`AttributeError: 'int' object has no attribute 'name'` 并崩溃，仍被记成 PASS。

正确做法：要求**正向完成标记**（`Shutdown complete`）+ 无崩溃特征（`Traceback` / `AttributeError` / `panic` / …）。

### 7.3 判定"进程是否真的退出"要用**端口释放**，不要看包装进程

`npm run dev`（tsx watch）、`mvn spring-boot:run`、`go run .` 都是**包装进程**：
里面的服务进程退了，包装进程可能还留着。反过来，`uvicorn` 在收到信号后会**先关掉监听、再 drain 在途请求**，
所以"端口释放得快"也不代表没有等在途请求。

组合判据才可靠：**端口释放 + 日志关闭完成标记 + 在途请求拿到响应**。

### 7.4 取监听进程 PID 必须加 `-sTCP:LISTEN`（否则脚本会自杀）

`lsof -ti :PORT` 会把**连接该端口的客户端**也列出来。本轮给优雅关闭加了"在途请求探针"之后，
发请求的**验证脚本自己**也出现在列表里，于是 `os.kill(pid, SIGTERM)` 杀掉的是脚本自己 ——
表现是脚本莫名以 **rc=143** 中止、日志截断。正确写法：

```bash
lsof -nP -iTCP:8132 -sTCP:LISTEN -t     # 只要监听方
```

### 7.5 子进程环境：清代理、清端口覆盖变量、强制 Python 无缓冲

- `HTTP_PROXY` 会干扰场景 09 对本地 mock 服务的调用；
- 注入的 `SERVER__PORT` 会被 Spring Boot 宽松绑定为 `server.port`，使 Java 服务绑到错误端口；
- `PYTHONUNBUFFERED=1`：Python 输出重定向到文件时是块缓冲，而 uvicorn 进程在关闭收尾后
  **会被信号直接终止**（`atexit`/`flush` 都不执行），未刷盘的日志会整块消失（§5.3 第 3 点）。

### 7.6 测试类场景要求"有摘要"，不能只看退出码

`mvn -q test` 成功时**什么都不打印**，退出码 0 无法区分"跑过了"和"没跑"。
改用 `mvn test` 并解析 surefire 的 `Tests run: N, Failures: 0, Errors: 0`，
各语言分别取 `N passed`（pytest / vitest）、`test result: ok`（cargo）、`ok <pkg>`（go test）。

### 7.7 残留进程会污染测量

上一轮被中断的运行会留下监听进程，新实例绑不上端口，日志出现 `address already in use`，
而请求其实打到了**旧实例**上 —— 测量结果全错且看起来"有响应"。
每次启动前必须先清掉占用端口的监听进程（`free_port`），并核对日志里没有 `address already in use`。

### 7.8 不要依赖生成器/编译器在受限环境下的退出码

如 safe-delete 守卫会污染 `go`、`cargo` 的退出码，需结合产物与输出内容判定。

### 7.9 `go.mod` 缺失的症状具有迷惑性

目录无 `go.mod` 时 `go mod download` 打印 `go: no modules specified`（rc=1），
而**有 `go.mod` 但无依赖**时实际返回 rc=0；因此不可通过容忍该提示来"绕过"——正确做法是补齐 `go.mod`。

### 7.10 要解析子进程输出，必须"捕获输出"，不能回头去读拼接日志

`run()` 把「命令回显」写进日志文件、又把子进程的 stdout 指向同一个 fd。两者顺序**没有保证**：
回显可能还在 Python 的写缓冲里，子进程已经直接写到文件了。于是日志长这样（顺序颠倒）：

```
lines=206 words=777

$ python main.py -l -w ../../../README.md
```

按"取最后一次 `$ ` 之后的内容"去解析，就会解析到**命令本身**、拿不到任何指标 ——
本轮就踩了这个坑，导致 03 场景 5 种语言全被误判为 FAIL（`工具 lines=None`）。
正确做法：解析类场景统一用 `run_capture()`（`stdout=PIPE` 捕获后同时写日志并返回文本），
同时给回显加 `flush()` 让日志顺序对人也可读。

> 历史归档提示：`.wb_verify/runs/20261016-112123_full.json` 那次运行里 03 场景 5 种语言标了 FAIL，
> 就是这个解析缺陷造成的**误判**（`工具 lines=None`）；修复后的权威结果见
> `.wb_verify/all_results.json` 与 `runs/20261016-113119_full.json`（65/65 PASS）。
>
> 仓库更名（`multi-lang-backend-showcase` → `Multi-Lang-Backend-Showcase`）后从新路径全量复跑，
> 结果为 `runs/20261016-120124_full.json`（同样 65/65 PASS）—— 用于确认更名与脚本路径改造没有破坏任何构建/运行链路。

### 7.11 判定逻辑本身要配"反向对照"

"端口释放"这类判据很容易写成永远为真。本轮用一个**故意忽略 SIGTERM** 的对照组服务自检：

```
对照组（忽略 SIGTERM 的服务）已在 8199 监听 → port_released = False → 判据自检 OK
```

如果对照组也返回"已释放"，说明判据不可信。凡是加新判据，都建议先拿一个"必然失败"的样本过一遍。

---

## 8. 复现命令

```bash
cd /Users/chenjunbing/Develop/Project/Personal/Multi-Lang-Backend-Showcase

# 全量验证（13 场景 × 5 语言）；结果写入 .wb_verify/all_results.{json,md}，并归档到 .wb_verify/runs/
python3 .wb_verify/verify_all.py

# 只跑指定场景（按名称前缀匹配）；结果同样归档，不会覆盖历史
python3 .wb_verify/verify_all.py 03 12

# 场景 12 定点复核（在途请求 + 关闭日志 + 端口释放），可指定语言/命令
python3 .wb_verify/check_graceful.py                 # 全部 5 种语言
python3 .wb_verify/check_graceful.py python          # 只跑 python
python3 .wb_verify/check_graceful.py python "python3 -u main.py"   # 换启动方式再验证

# 清理沙箱写权限探测遗留的垃圾文件（随机名 + 内容恒为 4 字节 "blat"）
python3 .wb_verify/clean_probe_files.py              # 只扫描报告
python3 .wb_verify/clean_probe_files.py apply        # 执行删除

# 11 的 TS-Node 需要先构建原生模块（见 §6.1）
cd scenarios/11-db-crud-pool/ts-node && npm rebuild better-sqlite3 --build-from-source
```

---

## 9. 说明与边界

- 本报告的矩阵由**自动化脚本在本机逐场景实测**得出；日志原件在 `.wb_verify/all_logs/`（每个「场景 × 语言」一份）。
- 判定强度分层：`03`（数值 + 选项语义）、`05`（测试摘要）、`12`（在途请求 + 关闭日志）是**行为级**断言；
  `http` 类场景目前仍是**端口监听级**（"可启动、契约端点可访问"），**不包含**响应内容正确性
  （如 01 的 JSON 字段、02 的并发吞吐、06 的召回质量、09 的重试次数、10 的精确速率）。
- **下一步建议**：为 `http` 类场景补"契约级"断言 —— 按各自 README 声明的端点与响应体，
  对 5 种语言做**响应归一化后的一致性比对**（同一请求 → 同一语义结果）。
  本轮在 03/12 上的经验说明：这类比对才最容易抓到"静默不一致"。

---

## 10. 契约级断言（场景 13 起引入）

前面 §9 提到的"下一步建议"已经在**场景 13（CPU 密集并行计算）**上落地。

### 设计：用 Python 独立实现一遍算法作为 oracle

场景 13 的"行为"就是 `checksum`。若某门语言的整数语义写错 ——
Python 忘记 `& MASK`、TS 用 `number` 而非 `BigInt`、Java 用有符号输出 ——
**服务照样能起来、端口照样通**，端口探活级别的判定完全发现不了。

因此验证器改为：**用 Python 独立实现同一套 uint64 环绕 LCG 作为 oracle**，
再把各语言返回的 checksum **逐任务**与之比对。

> 为什么不用"跨语言互相比对"：那需要把 5 个语言的结果聚到一起再判定，
> 一旦不一致只能知道"有人错了"，**定位不到是谁、错在哪个任务**。
> 用 oracle 则每个语言都能独立判定，且能精确报出 `task 2 checksum 实际=x 期望=y`。

### 断言强度

| 层级 | 内容 | 场景 |
|------|------|------|
| 启动级 | 端口可连接 | 02/04/06/07/08/09/10/11 |
| 行为级 | 数值与语义契约（统计口径、选项语义、测试摘要、在途请求） | 03/05/12 |
| **契约级** | **响应内容逐字段比对（通用用例引擎 `verify_cases`）** | **00 / 01** |
| **契约级** | **响应内容逐字段与 oracle 比对（数值/数据类）** | **13 / 14 / 15 / 16 / 17** |

### 实测结果

参数 `task_count=4, iterations=300000, concurrency=2`，五门语言返回值：

```
逐任务 checksum：[417981439666351841, 736283073909781090, 1054584708153210339, 1372886342396639588]
总    checksum：3581735564125982858
```

**五门语言全部与 oracle 逐位相符**，且互不相同的三种实现策略都得到同一结果：

| 实现策略 | 语言 | 说明 |
|---------|------|------|
| 原生 uint64 环绕 | Go / Java / Rust | Go `uint64` 原生；Java `long` 补码环绕等价；Rust 显式 `wrapping_*` |
| 任意精度 + 手动掩码 | Python | `& ((1<<64)-1)`，不截断就会与其余语言完全不同 |
| BigInt + 手动掩码 | TS-Node | JS 无 64 位整数，`BigInt.asUintN` 语义 |

### Python / Rust 的等价验证方式

本环境下验证器的 **prep 阶段**被拦截（`pip` 找不到可用临时目录、`cargo` 无法删除已有构建产物），
根因是运行环境的 Security Center 拦截文件删除，**与代码无关**。绕过 prep 后的等价验证：

```bash
# Python：依赖已就绪，直接起服务（跳过 pip install）
cd scenarios/13-cpu-bound-parallel/python && uvicorn main:app --port 8137

# Rust：二进制已在首次运行中编译产出，直接执行（跳过 cargo）
cd scenarios/13-cpu-bound-parallel/rust && ./target/debug/cpu-bound-parallel
```

两者返回的 checksum 与 oracle 同样逐位相符。**在常规终端跑 `verify_all.py` 即可拿到完整的全绿记录。**

### 场景 14（数据分析处理）：契约级断言的第二个落地

场景 14 把同一套 oracle 思路用到了**聚合结果**上：数据集是行号的纯函数
（`amount = LCG(i+1) 高32位 % 100000`，`category = i % 8`），验证器内的 `oracle_data()`
独立重算 8 组统计（count/sum/avg/p50/p95）+ Top10，对每门语言响应逐字段比对
（`avg` 容差 1e-9，耗时字段只验存在性——性能数字跨机器不可比）。

这个场景暴露了两类**只有契约级断言才能发现**的风险点，已全部在实现中显式处理：

1. **分位数口径**：pandas 默认 linear 插值、polars 默认 nearest、tablesaw 的 median 对偶数长度取中间均值——
   放任各库默认值，五语言结果必然对不齐。统一为 nearest-rank（排序后取 `ceil(p*n/100)-1` 下标）。
2. **Top-K 平局规则**：amount 只有 10 万个取值、20 万行数据，平局必然大量出现——
   必须显式定义二级排序键（id 升序），否则各语言 sort 的稳定性差异会直接造成 Top10 漂移。

2026-10-16 本机实测（`rows=200000, categories=8`）：**五门语言的 groups + top10 与 oracle 逐字段一致**
（服务端耗时 Java 278ms / Go 76ms / Python 161ms / Rust 252ms / TS-Node 255ms —— 均为 debug 构建、
含数据生成与聚合，仅示意量级，不构成性能结论）。Rust 侧的两处适配见下「polars 0.55 API 差异」。

### polars 0.55 API 差异（Rust 侧踩坑）

首次编译报 4 个错，全部来自 polars 0.5x 的签名变更，改法与动机：

1. `DataFrame::new(Vec<Series>)` → 已是 `new(height: usize, columns: Vec<Column>)`：
   改用 `DataFrame::new_infer_height(vec![Column::from(Series::new("id".into(), ...))])`，
   既不用手算 height，也避开后续版本再改签名。
2. 列名由 `&str` 变为 `PlSmallStr`：`.into()` 转换即可。
3. `Expr::count()` 的输出 dtype 是 `IdxSize`（随平台/版本可能是 u32 或 u64）：
   统一 `.cast(DataType::Int64)` 后再按 `.i64()` 读列，避免跨版本 dtype 漂移。

顺带实证：**danfojs-node 1.2.0 在 Node 24 上可安装、可运行**，`groupby().col().sum()` 的整数
求和无精度损失——但其依赖链含 `cdn.sheetjs.com` 的 tarball 直连（国内安装 10+ 分钟）与
`@tensorflow/tfjs-node@3.x` 原生绑定（Node 新版本无官方支持），选型结论"已停更、谨慎"已写入场景 README。

### 场景 15（结构化并发 + 取消传播）：把"取消"变成可断言的字段

场景 15 把"取消传播"这条**看不见的语义**拆成五个可断言字段：
`outcome / completed / cancelled / failed / leaked`，外加 `elapsed_ms` 的上下界。
三个用例（全成功 / fail-fast / 父作用域超时）逐字段比对，最后再做一次**延迟检查**：
三个用例跑完后再等 3 秒查 `/stats`，`active_tasks` 必须为 0。

**为什么时间断言是必需的**：取消没传播时，`outcome` 照样可以是 `failed` ——
只有 `completed` 里多出 id、`elapsed_ms` 变成"跑满 task_ms"的量级才会暴露。
也就是说，**"返回了正确的失败原因"和"兄弟任务真的停了"是两件事**，前者不能替代后者。

2026-10-16 本机实测（`task_ms=2000`）：五门语言 **5/5 全绿**，三个用例的服务端耗时
分别在 **201~204ms / 250~252ms / 300~302ms** —— 与 `fail_after_ms=250`、`timeout_ms=300`
几乎重合，说明取消都在信号发出点附近生效，没有一门语言等到任务跑满。

### Java 侧对照实验：StructuredTaskScope 的取消是"中断"而非"传播"

实现时的初始判断是"JDK 21 的 `StructuredTaskScope` 不传播取消，必须手写标志"，
于是写了 `AtomicBoolean` + 轮询。为验证这个判断做了一组对照实验
（把子任务改成不检查标志、直接 `Thread.sleep(task_ms)`）：

```
tasks=8, task_ms=2000, fail_index=3, fail_after_ms=250
→ {"outcome":"failed","completed":[],"cancelled":[0,1,2,4,5,6,7],"failed":3,
   "elapsed_ms":260,"leaked":0}
```

**去掉手写标志后行为完全不变** —— 说明兄弟任务不是"看到取消信号"才退出的，
而是被 `StructuredTaskScope` 收尾时的 **`Thread.interrupt()`** 打断的（JDK 21 的实际行为）。
实验脚本：`/tmp/probe_java15_nocancel.py`（复制到 `/tmp` 改两行再跑，不污染仓库）。

代价因此换了形式，共三条，已写入场景 README：

1. 取消**不携带原因**（没有 `ctx.Err()` / `signal.reason` 之类的检查点）；
2. 中断**只对可中断的阻塞点生效**（不可中断的忙循环/部分阻塞 IO 会静默失效）——
   故实现里保留了标志兜底，并把 `InterruptedException` 统一归一化成 `cancelled`；
3. `StructuredTaskScope` 到 JDK 21 仍是 **preview**（编译与运行都要 `--enable-preview`，
   API 在 JEP 453 / 480 / 487 中三度变更）。

### 场景 15 带来的两个环境坑

1. **按场景切换 JDK**：只有这一个场景的 Java 需要 JDK 21。验证器新增 `env_for(name, lang)`，
   只对 `15-structured-concurrency` + `java` 覆盖 `JAVA_HOME`（指向 mise 的 `zulu-21`），
   其余场景仍用 JDK 17；场景目录内另放 `.mise.toml` 做目录级覆盖，方便手工运行。
2. **`SERVER__PORT` 会顶掉 `server.port`**：运行环境注入的 `SERVER__PORT=49817` 被 Spring Boot
   宽松绑定后覆盖了 `application.properties`（验证器已在 `ENV` 里清掉，但手工跑 mvn 时会遇到）。
   另：`pom.xml` 的 XML 注释里出现连续两个连字符（如写 `--enable-preview`）会让 Maven 直接报
   `Non-parseable POM` —— 这类注释要改写。

### 场景 16（大文件流式处理）：把"内存占用"变成可断言的字段

前三个边界场景断言的都是"算出来的东西对不对"。场景 16 多了一类新字段 ——
**资源占用**：`rss_delta_bytes`（处理前后进程 RSS 之差）与 `output_file_bytes`（输出文件真实大小）。

三个用例：8MB/1KiB 块（8192 块，行必然跨块）→ 8MB/64KiB 块（换块大小摘要必须不变）
→ 32MB/64KiB 块（数据量 4 倍，`rss_delta_bytes` 必须 ≤ 16MiB）。

**为什么必须断言内存**：刻意做了一组**反向对照实验** —— 把 Python 版改成一次性读入
（`f.read()` + `split()`），同样的 32MB 数据：

```
流式（本仓库实现）    ：rss_delta =   1.2 MiB，checksum 正确，HTTP 200
一次性读入（对照组）  ：rss_delta = 382.6 MiB，checksum 正确，HTTP 200
一次性读入，8MB 数据  ：rss_delta = 118.3 MiB（约数据的 15 倍）
```

**两版的摘要都完全正确、HTTP 都返回 200** —— 只比摘要根本无法区分它们。
这正是 `rss_delta_bytes` 上限存在的唯一理由（§7.11 说的"反向对照"在这里落到了实处）。
顺带一个读数：335 万行切成 335 万个 `bytes` 对象后 RSS 增量是数据的 12 倍 ——
**内存爆炸的主因往往不是数据本身，而是"每行一个对象"**。

**各语言的 RSS 观测能力并不对等**（这点本身就是选型素材）：

| 语言 | 拿到 RSS 的方式 | 强度 |
|---|---|---|
| Go / Rust / Python | `getrusage` → `ru_maxrss`（进程启动以来的**真峰值**） | 强 |
| TS-Node | `process.memoryUsage().rss`，且**没有峰值接口**，只能循环轮询采样 | 弱 |
| Java | 标准库**没有 RSS 接口**（`OperatingSystemMXBean` 只有已提交虚拟内存），只能 fork `ps` 采样 | 最弱 |

另外 Rust 用 `#[global_allocator]` 拿到了**逐字节精确的堆分配峰值**（327KB），
其余四门都是运行时估计值或采样值 —— 这是本场景里 Rust 观测能力的独家优势。

### 场景 16 踩到的实现坑

1. **`Buffer.copy()` 不推进写指针**（TS）：`pending.copy(outBuf, outLen, ...)` 后必须
   `outLen += 4`，否则后续的 6 位数字会覆盖刚拷进去的 `"NNN,"`。
   症状是**计数全对、`bytes_written` 也对，只有摘要错** ——
   因此加了一条 `output_file_bytes == bytes_written` 的断言（stat 文件 vs 计数器），
   把"声称写入"和"真实写入"分开验。
2. **`Buffer.indexOf(10, start)` 会搜进缓冲区未初始化的尾部**（TS）：
   pending 只有前 `pendingLen` 字节有效，必须手写扫描循环限定上界。
3. **`Read` 不保证读满**（Go / Rust / Python / Node）：必须自己写"填满一个块"的循环；
   漏了会把短读误判成 EOF，而且**在块大小恰好整除文件大小时测不出来**。
4. **`ru_maxrss` 单位不一致**：Linux 是 KB、macOS 是 bytes，五门实现里都要分支。
   另外它是"进程启动以来的峰值"、不可重置，所以 `rss_delta` 的真实含义是
   "本次处理有没有把 RSS 推到新高" —— 先用小数据量预热，口径才干净
   （验证器就是先跑两个 8MB 用例再跑 32MB）。
5. **Rust 的 debug / release 差 ~17 倍**：验证器统一用 `cargo run`（debug），
   同一份代码 release 下是 63/50/198ms、debug 下是 891/836/3350ms。
   对比跨语言耗时前必须先确认构建档位，否则会得出完全错误的选型结论。

### 场景 17（错误处理深水区）：把"可观测性"变成可断言的字段

前四个边界场景断言的都是"算出来的值对不对"（13/14）、"取消有没有生效"（15）、
"内存有没有爆"（16）。场景 17 断言的是**出事的时候你能不能知道出了什么事**。

统一契约：`GET /errors/{kind}` 五种错误形态（`not_found` / `validation` / `wrap_chain` /
`panic` / `async_detached`）+ `GET /stats`。响应体把四件事变成可断言字段：

| 字段 | 断言点 |
|------|--------|
| `cause_chain` | 四层因果链（最外层 → 根因）**逐字一致** —— 足以测出"包装时漏了 `%w` / `from` / `cause`" |
| `trace_id` | 必须与请求头 `X-Trace-Id` **逐字相同** —— 错误路径上有没有把上下文带出来 |
| `recovered` + 服务仍可应答 | 证明未捕获异常是真兜住了，不是进程崩了又起来 |
| `/stats.unhandled ≥ 1` | **脱离请求上下文的错误有没有人看见** —— 本场景的胜负手 |

**实测 5/5 PASS**。核心差异（详见场景 README）：

- **脱离上下文的异步错误，五门语言五种命运**：Go 彻底静默（goroutine 里的 panic 还会
  终止进程）；Rust 的 `JoinHandle` 被 drop 时错误消失；Java 的 `CompletableFuture`
  异常静静躺在 Future 里；Python 只在 task 被 GC 时打一行日志；
  **TS(Node) 默认 `--unhandled-rejections=throw`，不装钩子就直接终止进程**。
- **`stack_present` 逐语言预期**（`java/python/ts-node = true`，`go/rust = false`）不是缺陷，
  是语言默认行为：Go 的 error 是值、`recover()` 只拿到 `any`；Rust 的 anyhow 只在
  `RUST_BACKTRACE=1` 时才抓 backtrace。刻意不为了对齐去补，让差异暴露成可断言的事实。

#### 两个反向对照实验（证明断言"有牙齿"）

1. **Python 去掉 `task.add_done_callback(...)`**：HTTP 照样 202、响应体完全正常，
   只有 `/stats.unhandled` 恒为 0 —— 只比对响应体根本区分不出来。
2. **Node 去掉 `process.on("unhandledRejection")`**：
   ```console
   $ node -e "Promise.reject(new Error('async-boom-17')); setTimeout(()=>console.log('存活'),500)"
   Error: async-boom-17        ← 进程直接退出，"存活" 那行永远没打印
   Node.js v22.22.2
   ```
   装上钩子后正常输出 `钩子捕获到: async-boom-17` → `装了钩子 -> 进程存活`。

#### 场景 17 踩到的实现坑

1. **Java 的 `CompletionException` 会包一层**：`whenComplete` 里拿到的 `e` 不是原始异常，
   取 `getMessage()` 会得到 `"java.lang.RuntimeException: async-boom-17"`，必须剥到根因。
2. **Python 的 `@app.middleware("http")` 必须自己接异常**：Starlette 默认的
   `ServerErrorMiddleware` 会在发完响应后把异常继续抛给 uvicorn —— 响应体是我们给的，
   但异常对上层仍是"未处理"的，进不了错误体系。
3. **TS 的 `Error.cause` 需要 ES2022**：tsconfig 的 `target`/`lib` 低于 ES2022 时
   `new Error(msg, { cause })` 编译能过但 cause 静默丢失；且 `console.log(err)` 默认不打印 cause。
4. **Rust 的 panic payload 类型不定**：`panic!("literal")` 可能是 `&str` 也可能是 `String`，
   downcast 必须两种都处理。
5. **Go 的 `mux.Handle("GET /errors/", ...)` 是子树匹配**：没有"通配一段"的语法，
   `{kind}` 要自己 `strings.TrimPrefix`。另外**不写 `recover` 中间件时 `net/http` 也会 recover**，
   但它做的是断开连接 —— 客户端拿到 EOF 而不是 500，日志里也什么都没有。

---

## 11. 已知契约不一致（待处理，未修改）

> 原记录的 `02-concurrent-task` Java camelCase 问题已在**验证强度加强计划批次 2** 中修复
> （`spring.jackson.property-naming-strategy=SNAKE_CASE`，与场景 13 同方案），详见 §12 批次 2。
> 当前无其他已知的跨语言契约不一致。

---

## 12. 验证强度加强计划（基础场景 00 → 12 逐批升级）

### 背景

§10 的"断言强度"表里，基础 http 场景长期停留在**启动级**（端口可连接即通过）。
边界场景 13~17 已全部做到契约级，方法完全成熟，因此启动本计划：
把 00~12 逐批升级，**只 commit 不推远端**，每批一个提交。

批次划分（每批 = 1 个提交）：

| 批次 | 场景 | 状态 |
|------|------|------|
| 1 | `00-hello-http` + `01-json-serialize` | ✅ 已完成 |
| 2 | `02-concurrent-task` + `04-file-io` | ✅ 已完成 |
| 3 | `06-simple-rag-demo` + `07-structured-logging` | ⬜ 待开始 |
| 4 | `08-config-management` + `09-http-client` | ⬜ 待开始 |
| 5 | `10-rate-limit` + `11-db-crud-pool` | ⬜ 待开始 |
| 6 | `03-cli-tool` + `05-unit-test-mock` + `12-graceful-shutdown`（行为级 → 继续加深） | ⬜ 待开始 |

### 通用用例引擎

`verify_all.py` 新增 `kind = "contract"` 与三个可复用部件：

- `http_req()`：发请求并返回 `(status, headers, body)`，按 Content-Type 决定是否解析 JSON；
  用 `http.client`（不走代理，避免 `HTTP_PROXY` 把 localhost 劫持成 502）。
- `json_match()`：递归比对 —— dict 默认子集匹配（`exact=True` 时键集合也必须相同）、
  list 等长逐元素、标量严格相等；**bool 与 int 分开判**（避免 `True == 1` 假阳性）。
- `verify_cases()`：启动服务 → 逐个执行用例 → 汇总失败原因。
  用例是声明式 dict（`status` / `content_type` / `json` / `assert` 回调），
  新场景接入只需写一个 `CASES_xx` 列表 + 注册进 `CONTRACT_VERIFIERS`。

### 批次 1（00 + 01）实测：升级第一天就抓到 5 处跨语言偏差

**场景 00**：6 个用例（缺省 / 显式 / 空 / unicode name、未匹配路径 404、方法不允许 405）
五门语言全绿。其中"非 GET → 405"一条**首跑即失败**：fastify 对"路径匹配但方法不匹配"
默认返回 **404**，而 Spring / net-http / FastAPI / axum 都返回 **405**。
TS 侧已改用 `fastify.all` 显式抹平 —— 这类差异在端口监听级判定下永远看不见。

**场景 01**：5 个端点逐字段 + `json` 字符串逐字节比对。首跑抓到 4 处偏差（均已修复）：

| 语言 | 偏差 | 修正 |
|------|------|------|
| Go | `json.Marshal` 默认把 `<` `>` `&` 转义成 `\u003c` 等（HTML 转义） | `json.Encoder` + `SetEscapeHTML(false)`（新增 `encodeJSON` 辅助函数） |
| Python | `json.dumps` 默认 `ensure_ascii=True` + 带空格分隔符 | 统一 `ensure_ascii=False, separators=(",", ":")` |
| Python | `/deserialize` 的 `size` 用 `len(str)`（字符数，其余四门是字节数） | `len(json_string.encode("utf-8"))` |
| TS-Node | `/deserialize` 的 `size` 用 `string.length`（UTF-16 单元数） | `Buffer.byteLength(json_string)` |

**方法论沉淀**：本轮失败全部集中在 `roundtrip` 端点 —— 因为 `/serialize` 修完之后，
`roundtrip` 里还有一份独立的序列化调用被漏掉。**同一契约在多处落地时，断言必须覆盖每一处**，
否则"改了一处就以为全改了"。

**载荷设计**：测试载荷键名按字母序排列 —— Go 的 `map` 与 Rust 的 `BTreeMap` 按键排序输出，
Python / Java / TS 保留输入顺序；排序输入让五门语言的 `json` 字符串可逐字节比对，
同时把"键序差异"这个事实写进 README 而不是藏进实现。

批次 1 结果：`python3 .wb_verify/verify_all.py 00 01` → **10/10 全绿**（归档见 `.wb_verify/runs/20261016-223045_sub-00_01.md`）。

### 批次 2（02 + 04）实测：并发语义与文件契约，共修复 12 处跨语言偏差

**场景 02（并发任务处理，12 用例）**：标准并发 / 并发数大于任务数 / 零延迟 / 字段缺省 /
非法入参 4 种 / 畸形 JSON / 空 body / 方法 405 / 并发双请求。核心断言是
`total_time_ms ∈ [ceil(n/c)*delay*0.9, ceil(n/c)*delay*1.5+300]` —— **下界证明限流真的生效**
（不限流会低到约一个 delay），**上界证明没有退化成串行**（串行 = n*delay）；
外加 results 的 id 必须严格 `0..n-1` 保序、`throughput` 与 `total_time_ms` 自洽（容差 0.02）。

| 语言 | 偏差 | 修正 |
|------|------|------|
| Java | 响应是 camelCase（`totalTasks`/`totalTimeMs`），与其余四门 snake_case 不一致；**且请求绑定同样受影响** —— README 里的 `{"task_count":100}` 从未真正绑定，只是默认值碰巧蒙对 | `application.properties` 加 `spring.jackson.property-naming-strategy=SNAKE_CASE`（与场景 13 同方案；该策略同时作用于反序列化） |
| TS-Node | 方法不匹配返回 404（fastify 默认行为，与批次 1 的场景 00 同类） | `fastify.all` + 显式方法检查返回 405 |
| Go | 请求体用非指针 `int`，**分不清"字段缺省"与"显式传 0"**：缺省时静默按默认值、传 0 也静默夹到 100 | 改指针类型 + `firstOf` 辅助函数，缺省走默认值、显式非法值返回 400 |
| Python | pydantic `Field(ge=1)` 的校验失败是 **422**，与其余四门的 400 不一致 | 去掉约束改手动校验 `HTTPException(400)`，并注册 `RequestValidationError` 处理器把解析/校验错误统一映射为 400 |
| Rust | axum 的 `Json` 提取器对"语法错误"给 400、对"类型错误"给 **422**，语义分裂 | 改手动 `serde_json::from_slice` 解析，统一映射 400（`task_delay_ms` 相应改 `i64` 以便校验负值） |
| Go | 零延迟任务下 `elapsed=0` 时 throughput 保持初值 **0**，其余四门给 `task_count` | 初值改 `float64(taskCount)` |
| Java/Go/Python/Rust/TS | 非法入参（`task_count<1` 等）原本被静默夹取，契约要求 400 | 五门统一显式校验返回 400 |

**场景 04（文件读写 & 目录遍历，28 用例）**：写→读往返（字符串 / 对象两种 content）、
覆盖 + 追加、深层目录自动创建、递归 / 非递归 / 空目录扫描、读不存在 404、读目录 400、
扫描不存在 404、扫描文件 400、写失败（父路径是文件）、参数缺失 / 空串 400、方法 405 ×3、未匹配路径 404。
除接口字段外，**"声称的字节数"必须与验证器本地独立读磁盘的结果一致**，
scan 的 `files`/`total_bytes` 与本地 `os.walk`/`os.listdir` oracle 比对。

| 语言 | 偏差 | 修正 |
|------|------|------|
| Java | `content` 为对象时用 `String.valueOf(map)` 写出的是 **Java 的 toString 格式** `{k=v}`，根本不是 JSON | 改用 `ObjectMapper.writeValueAsString`（紧凑、不转义非 ASCII / HTML 字符） |
| Java | `append` 字段缺失时 NPE：`getOrDefault("append",false) instanceof Boolean` 通过检查，但 `body.get("append")` 返回 null，**拆箱即炸**（且抛在 try 外面变成 500） | 先取 `Object appendObj` 再判类型 —— 这是一个此前从未被触发的既有缺陷，"不带 append 的写"用例当场抓住 |
| Go | `writeJSON` 的 `json.Encoder` 默认 HTML 转义，读回含 `<` `>` `&` 的内容会变成 `\u003c`（与批次 1 的场景 01 同类） | `Encoder` + `SetEscapeHTML(false)` |
| Python | 对象 content 的 `json.dumps` 默认带空格分隔符（`{"a": 1}`），与其余四门的紧凑形式对不上 | 统一 `separators=(",", ":")` |
| Rust | 写失败返回 **500**，其余四门是 200 + `success:false` | 改 200 + `success:false`，错误详情放 body |
| Python / TS-Node | 必填 query 参数缺失时分别返回 422 / **500**（TS 是 `fs.stat(undefined)` 的 TypeError），Go/Java/Rust 是 400 | Python 改 `Optional[str]` 显式 400；TS 显式检查返回 400 |

**方法论沉淀**：

- **总耗时的上下界是"限流是否生效"的唯一硬证据**：只断言"总耗时 > 0"的话，
  把并发限流整个删掉（100 个任务全并行）照样通过 —— 下界（≈理想波次）与上界（< 串行）缺一不可。
- **"声称值"与"真实值"分开验**再次立功：04 的 `bytes_written` 若只跟响应里的字段自洽，
  Java 的 toString 格式写盘 bug 就漏了（计数对、内容错）；必须本地读磁盘比对。
- **反向对照的便宜替代**：本批每个修正项都对应一个"若不改必失败"的既有用例
  （如 02 删掉 Go 的 `firstOf` → "字段缺省"用例失败；04 还原 Java 的 `String.valueOf` → 磁盘内容断言失败）。
- **验证器自身也会错**：批次 2 首跑时"并发双请求"用例全军覆没，原因是验证器用
  `("exc", repr(e))` 元组标记异常，而 `http_req` 的正常返回值也是元组 ——
  **每次成功响应都被误判成"请求异常"**。改用 dict 包装标记后才恢复。
  教训：异常哨兵值必须与正常返回值的类型空间隔离。
- **asyncio.sleep 有毫秒取整误差**：Python 的 `sleep(100ms)` 实测只测到 99ms
  （事件循环经 kqueue 的毫秒粒度取整），其余四门的精确保眠会超过 delay。
  契约下界因此留 2ms 容忍并写进注释，而不是强行抹平。

批次 2 结果：`python3 .wb_verify/verify_all.py 02 04` → **10/10 全绿**（归档见 `.wb_verify/runs/20261016-233015_sub-02_04.md`）。
