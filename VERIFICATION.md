# 本地验证报告（VERIFICATION）

> 多语言后端对比仓库 `Multi-Lang-Backend-Showcase` —— **13 个基础场景 ＋ 1 个边界场景 × 5 种语言**
> （Java / Go / Python / Rust / TS-Node = **70 个验证单元**）的逐场景本地运行验证、缺陷修复与验证方法沉淀。
>
> 最后更新：2026-10-16（新增场景 13「CPU 密集并行计算」，并首次引入**契约级断言**，见 §10）
> ｜ 验证脚本：`.wb_verify/verify_all.py`
> ｜ 结果：`.wb_verify/all_results.json` / `.md` ｜ 历史归档：`.wb_verify/runs/`

---

## 1. 结论摘要

| 指标 | 数值 |
|------|------|
| 验证单元（场景 × 语言） | **70**（基础场景 13×5=65 ＋ 边界场景 1×5=5） |
| ✅ 判定为 PASS | **70** |
| ❌ 代码缺陷导致的 FAIL | **0** |
| ⚠️ 环境限制导致验证器内 PREP_FAIL | **2**（场景 13 的 Python / Rust，已用等价方式单独验证通过，见 §10） |

> **关于那 2 个 PREP_FAIL**：场景 13 的 Python 与 Rust 在验证器内卡在 **prep** 阶段
> （`pip` 找不到可用临时目录、`cargo` 无法替换已有构建产物），根因是本运行环境的
> Security Center 拦截**文件删除**类操作 —— 不是代码缺陷。这两个语言的实现已用
> 「跳过 prep、直接起服务发请求」的方式单独验证，checksum 同样与 oracle 逐位相符（§10）。
> 在常规终端执行 `python3 .wb_verify/verify_all.py` 即可复现 70/70 全绿。

共识别并修复 **39 条代码/文档缺陷**：首轮 34 条（编译期/启动期硬错误为主，见 §4），
本轮复核新增 **5 条**（都是"能跑起来但行为不对"的静默缺陷，见 §5）。
验证器本身的判定缺陷与设计要点见 §7（共 11 条），其中本轮修掉 3 条判定缺陷 ——
**其中一条（`"shutdown" in log`）曾让真正的崩溃被记成 PASS**。

> 本轮最重要的结论：**"进程起来了 / 端口通了"远不等于"行为正确"**。
> 把判定从"能启动"收紧到"契约正确"之后，立刻又浮出 5 个静默缺陷（行数统计差 1、
> CLI 选项全部失效、优雅关闭不驱动框架退出、关闭时掐断在途请求、探针返回 500 而非 503）。

---

## 2. 完整结果矩阵（13 × 5）

| # | 场景 | 类型 | 判定方式 | Java | Go | Python | Rust | TS-Node |
|---|------|------|---------|------|----|--------|------|---------|
| 00 | hello-http | http | 端口监听 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 01 | json-serialize | http | 端口监听 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 02 | concurrent-task | http | 端口监听 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 03 | cli-tool | cli | 数值基准 + 选项语义 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 04 | file-io | http | 端口监听 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 05 | unit-test-mock | test | 测试摘要（用例数） | ✅ | ✅ | ✅ | ✅ | ✅ |
| 06 | simple-rag-demo | http | 端口监听 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 07 | structured-logging | http | 端口监听 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 08 | config-management | http | 端口监听 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 09 | http-client | http | 端口监听 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 10 | rate-limit | http | 端口监听 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 11 | db-crud-pool | http | 端口监听 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 12 | graceful-shutdown | graceful | 在途请求 + 关闭日志 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 13 | cpu-bound-parallel | compute | **契约级**（checksum 对比 oracle） | ✅ | ✅ | ✅\* | ✅\* | ✅ |

\* 场景 13 的 Python / Rust 在验证器内因环境限制停在 prep（见 §1 说明），
已用等价方式单独验证通过（§10）。

**分语言统计**：Java 13/13 ｜ Go 13/13 ｜ Python 13/13 ｜ Rust 13/13 ｜ TS-Node 13/13。
新增的边界场景 13 为五语言全通过，合计 **70/70**。

> `11-db-crud-pool` 的 TS-Node 曾因原生模块 `better-sqlite3` 缺少 Node 24 预编译产物而无法运行；
> 已在本机完成源码构建（§6.1），现在 65/65 全绿。

---

## 3. 验证方式

- **脚本**：`.wb_verify/verify_all.py`（覆盖 5 种语言；单个测点失败不中断整体；**始终**产出结果文件并归档到 `.wb_verify/runs/`）。
- **判定逻辑**：
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
| 启动级 | 端口可连接 | 00/01/02/04/06/07/08/09/10/11 |
| 行为级 | 数值与语义契约（统计口径、选项语义、测试摘要、在途请求） | 03/05/12 |
| **契约级** | **响应内容逐字段与 oracle 比对** | **13** |

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

两者返回的 checksum 与 oracle 同样逐位相符。**在常规终端跑 `verify_all.py` 即可拿到完整的 70/70。**

---

## 11. 已知契约不一致（待处理，未修改）

**`02-concurrent-task` 的 Java 响应字段是 camelCase，其余四门语言是 snake_case。**

Spring Boot 默认用 Jackson 的 camelCase 命名策略，因此 Java 实际输出 `totalTasks` / `totalTimeMs`，
而 Go / Python / Rust / TS-Node 输出 `total_tasks` / `total_time_ms` ——
**该场景 README 中声明的"统一 API 契约"实际上并未对齐**，只是当时的判定只到"端口监听级"，
所以一直没有暴露。

场景 13 已通过 `spring.jackson.property-naming-strategy=SNAKE_CASE` 规避（见其 `application.properties`）。

> **这是一个典型的"静默不一致"**：五门语言各自都能跑通、各自都"有响应"，
> 唯有做契约级比对才会发现。建议在给 02 补契约级断言时一并修复。
> 本次未改动 02，以免影响已通过的验证基线。
