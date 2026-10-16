# 场景 17：错误处理深水区

> **一句话**：把"错误"从"打印一行日志"升级成**可断言的契约** ——
> 错误的类型、因果链、上下文、可观测性，五门语言的差距比"能不能跑"大得多。

## 为什么这个场景能突出技术选型

前四个边界场景考的是"算得快不快、占多少内存、取消传不传得下去"。
错误处理考的是另一件事：**出事的时候，你能不能知道出了什么事**。

大多数人对错误处理的理解停留在"try/catch 一下"。真正的分水岭在四个地方：

1. **错误有没有类型** —— 调用方能不能靠类型系统知道"这里可能失败"
2. **因果链会不会断** —— 一层包装没写对，根因就永远找不回来
3. **上下文穿不穿得过去** —— trace_id 在错误路径上丢了，日志就是一堆孤儿
4. **脱离请求上下文的错误谁能看见** —— 异步任务里的错误，五门语言的处理**完全不同**

第 4 条是本场景最硬的差异，也是唯一一条"不写代码就必然静默"的。

---

## 统一契约

### `GET /errors/{kind}`

请求头 `X-Trace-Id` 可选；不传时服务端生成 `tid-N`。

| kind | HTTP | code | 说明 |
|---|---|---|---|
| `not_found` | 404 | `NOT_FOUND` | 领域错误，单层 cause |
| `validation` | 400 | `VALIDATION_FAILED` | 带字段级 details |
| `wrap_chain` | 500 | `WRAPPED` | 四层包装的 cause 链 |
| `panic` | 500 | `INTERNAL` | **未捕获异常**，必须被兜底且进程存活 |
| `async_detached` | 202 | `ACCEPTED` | 错误发生在脱离请求上下文的异步任务里 |

响应体（五门语言逐字段一致）：

```json
{
  "kind": "wrap_chain",
  "code": "WRAPPED",
  "message": "handler: GET /errors/wrap_chain",
  "trace_id": "v17-go-3",
  "cause_chain": [
    "handler: GET /errors/wrap_chain",
    "service: get profile",
    "repository: load user",
    "db: row 42 not found"
  ],
  "details": [],
  "stack_present": false,
  "recovered": false
}
```

字段语义：

| 字段 | 含义 |
|---|---|
| `cause_chain` | **最外层 → 根因**。四层必须逐字一致 —— 这条就足以测出"包装时漏了 `%w` / `from` / `cause`" |
| `trace_id` | 原样回显请求头。**错误路径上有没有把上下文带出来**，第一次变成可断言的事实 |
| `details` | 字段级校验错误；非 validation 场景必须是 `[]`（不能是 null） |
| `stack_present` | 该错误是否携带调用栈。**逐语言不同，不是缺陷**（见下表） |
| `recovered` | 这个响应是不是"从崩溃边缘救回来的" |

### `GET /stats`

```json
{
  "handled": 4,
  "unhandled": 1,
  "panics_recovered": 1,
  "last_unhandled": "async-boom-17",
  "last_trace_id": "v17-go-5"
}
```

- `handled`：进了处理器的错误（`not_found` / `validation` / `wrap_chain` / `panic` = 4）
- `unhandled`：**脱离请求上下文**的错误数 —— 本场景的胜负手
- `panics_recovered`：从崩溃边缘救回来的次数

> **端口**：Java 8155 ｜ Go 8156 ｜ Python 8157 ｜ Rust 8158 ｜ TS-Node 8159

---

## 五门语言怎么实现的

### 错误类型：谁把"可能失败"写进了类型系统

| 语言 | 机制 | 代价 |
|---|---|---|
| **Rust** | `Result<T, E>` —— **编译期强制**，`?` 只能用于实现了 `Error` 的类型 | 错误类型必须出现在函数签名里。跨层要么统一成 `anyhow::Error`（丢静态类型），要么写枚举把每层列出来（样板多） |
| **Java** | checked exception —— 也是编译期强制 | 每一层都要重新声明或包装。真实项目里大量出现 `catch { throw new RuntimeException(e); }` 这种机械代码，最后退化成 unchecked |
| **Go** | `error` 是**普通接口值**，函数返回 `(*T, error)` 只是约定 | 不返回 error 也编译得过。带 code / details 只能自建结构体 |
| **Python** | 异常，签名不声明 | 调用方只能靠文档。漏掉的异常一路穿到最外层才暴露 |
| **TS** | `throw` 可以扔**任何值** | `throw "oops"` 完全合法；`catch (e)` 里 `e` 是 `unknown`，`e.message` 这一行就是事故源头 |

### 因果链：怎么包装，以及怎么断

| 语言 | 写法 | 断链的方式（都很常见） |
|---|---|---|
| **Go** | `fmt.Errorf("...: %w", err)` | 写成 `%v` 链就断在那里，**编译器不提醒** |
| **Rust** | `anyhow` 的 `.context("...")` | 不用 `anyhow` 就得自己实现 `source()`，样板量劝退很多人 |
| **Java** | `new XxxException(msg, cause)` | 只写 `new XxxException(msg)` —— 栈还能打出来，**cause 没了** |
| **Python** | `raise ... from err` | 漏掉 `from` → 只剩 `__context__`。**traceback 打出来看着一模一样**，但程序化的 `__cause__` 链是断的 |
| **TS** | `new Error(msg, { cause })` | tsconfig 的 `target` 低于 ES2022 时静默失效（编译能过，链是断的）；而且 `console.log(err)` **默认不打印 cause** |

> **Python 那条最阴**：`__context__` 是"处理另一个异常时又抛了"的隐式上下文，
> 不是因果关系。本实现刻意只认 `__cause__`，把两者混进链会让 `cause_chain` 不可预期。

### 未捕获异常：怎么兜底，兜住之后还剩什么

| 语言 | 兜底机制 | 兜住后拿到什么 |
|---|---|---|
| **Go** | `defer recover()` 中间件 | 一个 `any`：**没有类型、没有栈、没有 cause**。要栈得 `debug.Stack()` 现抓（开销不小） |
| **Rust** | `catch_unwind`（`tower_http::CatchPanicLayer` 内部也是它） | payload 需要自己 downcast（`&str` / `String` 两种都可能） |
| **Java** | `@RestControllerAdvice` + `@ExceptionHandler` | 完整的异常对象：类型、message、cause 链、栈全在 |
| **Python** | `@app.middleware("http")` 里 try/except 包住 `call_next` | 完整异常对象 + traceback |
| **TS** | fastify 的 `setErrorHandler` | `Error` 的话有 stack；**扔的不是 Error 就只有 `String(err)`** |

**Go 的坑值得单独说**：不写 `recover` 中间件，`net/http` 也会 recover —— 但它做的是
**把这条连接断掉**。客户端拿到的是 EOF 而不是 500，服务端日志里也没有这条错误。

### ⭐ 脱离请求上下文的异步错误：五门语言，五种命运

这是本场景的核心。代码里"起一个后台任务、它失败了"，没人 await 的时候会发生什么：

| 语言 | 默认行为 | 想观测到它，必须手写什么 |
|---|---|---|
| **Go** | **彻底静默**。goroutine 里的 panic 还会**直接终止整个进程** | `defer recover()` + `if err != nil { 记下来 }`，少一行就永远不会有人知道 |
| **Rust** | `JoinHandle` **被 drop 时错误静默消失**，编译器不提醒、运行时不告警 | 再 spawn 一个"看护"任务专门去 `await` 它 |
| **Java** | `CompletableFuture` 里的异常静静躺在 Future 里，直到有人 `join()` 才炸 | `.whenComplete((v, e) -> ...)` 或 `.exceptionally(...)` |
| **Python** | 只在 task 被 GC 时打一行 `Task exception was never retrieved` | `task.add_done_callback(...)` |
| **TS(Node)** | **Node ≥ 15 默认 `--unhandled-rejections=throw`，直接终止进程** | `process.on("unhandledRejection", ...)` |

> **TS 是五门里唯一"默认失败得很大声"的** —— 这反而更好：不做处理你会立刻发现。
> 但代价是漏了那一钩子，掉的不是一条错误，是整个服务。

#### 对照实验：证明这两个断言"有牙齿"

**实验 A（Python，去掉 `add_done_callback`）**：

```
async_detached -> HTTP 202 {"kind":"async_detached","code":"ACCEPTED", ...}
stats          -> {"handled":0,"unhandled":0,"panics_recovered":0, ...}
```

HTTP 照样 202、响应体完全正常 —— **只有 `unhandled=0` 暴露了它**。
这就是验证器里那条断言存在的理由：只比对响应体根本区分不出来。

**实验 B（Node，去掉 `unhandledRejection` 钩子）**：

```console
$ node -e "Promise.reject(new Error('async-boom-17')); setTimeout(()=>console.log('存活'),500)"
Error: async-boom-17        ← 进程直接退出，"存活" 那行永远没打印
    at [eval]:1:16
Node.js v22.22.2
```

装了钩子之后：`钩子捕获到: async-boom-17` → `装了钩子 -> 进程存活`。

---

## 各语言的取舍（一句话版）

| 语言 | 最舒服的地方 | 最难受的地方 |
|---|---|---|
| **Rust** | `Result` 让"必须处理"成为编译期要求；`?` + `context` 的组合很顺 | 错误类型要进签名；`JoinHandle` drop 就静默丢错误；默认没有 backtrace |
| **Java** | `@RestControllerAdvice` 把"错误 → 响应"彻底从业务代码抽走，控制器里一个 try/catch 都不用写 | 编译期的 checked exception 在这套"全抛出去"的写法面前形同虚设；异常带栈是有成本的 |
| **Go** | 错误就是值，零魔法、零依赖 | code / details / stack 全要自建；`%w` 漏一个就断链；goroutine 错误无钩子 |
| **Python** | 异常自带 traceback，`raise ... from` 表达因果很自然 | 漏 `from` 就只有 `__context__`；asyncio task 错误无钩子；签名不声明能抛什么 |
| **TS(Node)** | unhandledRejection 默认**打挂进程**，不给你机会假装没事 | `throw` 能扔任何值；`cause` 需要 ES2022；`console.log(err)` 不显示 cause |

---

## 验证方式（契约级）

`python3 .wb_verify/verify_all.py 17` → **5/5 PASS**。

断言的不只是返回值，还有**可观测性**：

1. 五个用例逐字段比对（HTTP 状态、code、message、`cause_chain` 四层、`details`、`recovered`）
2. `trace_id` 必须与请求头 `X-Trace-Id` **逐字相同**（上下文有没有穿过错误路径）
3. `stack_present` 逐语言预期：`java / python / ts-node = True`，`go / rust = False`
4. `panic` 之后服务必须还能应答 —— 证明是真兜住了，不是进程崩了重起的
5. `async_detached` 之后轮询 `/stats` 要求 `unhandled ≥ 1` 且 `last_unhandled == "async-boom-17"`
6. `/stats` 的 `handled == 4`、`panics_recovered == 1`、`last_trace_id` 回显最后一次请求

### `stack_present` 为什么逐语言不同

这不是实现缺陷，是**语言层面的默认行为**：

- **Java / Python / TS**：异常对象天生带栈（`getStackTrace()` / `__traceback__` / `Error.stack` 恒非空）
- **Go**：`error` 是值，不带栈；`recover()` 拿到的也只是个 `any`。要栈得 `debug.Stack()` 现抓
- **Rust**：`anyhow` 只在 `RUST_BACKTRACE=1` 时才抓 backtrace —— 默认关闭，这是**零成本**的设计

本实现刻意不为了"对齐"去给 Go 抓栈、给 Rust 开 `RUST_BACKTRACE`：
保留默认值才能把这个差异暴露成可断言的事实。

---

## 已知坑（复用）

- **`Error.cause` 需要 ES2022**：tsconfig 的 `target` / `lib` 低于 ES2022 时，
  `new Error(msg, { cause })` 编译能过但 cause 静默丢失。而且 `console.log(err)` 默认不打印 cause，
  排查时极易误判"没有根因"。
- **Go 的 `mux.Handle("GET /errors/", ...)`** 用的是子树匹配（路径以 `/` 结尾），
  要拿 `{kind}` 得自己 `strings.TrimPrefix` —— Go 1.22 的新路由写法对"通配一段"的支持有限。
- **Rust 的 panic payload 类型不定**：`panic!("literal")` 可能是 `&str` 也可能是 `String`，
  downcast 必须两种都处理。
- **Java 的 `CompletionException` 会包一层**：`whenComplete` 里拿到的 `e` 是
  `CompletionException`，真实异常在 `getCause()` 里，取消息时必须剥开。
- **Python 的 `@app.middleware("http")` 必须自己接异常**：Starlette 默认的
  `ServerErrorMiddleware` 会在发完响应后把异常继续抛给 uvicorn ——
  响应体是我们给的，但异常还是"未处理"的，进不了你的错误体系。
- **Java 响应是 snake_case 靠配置**：`spring.jackson.property-naming-strategy=SNAKE_CASE`
  （record 的 `traceId` → `trace_id`）。不加这个配置就会变成 camelCase，与其余四门不一致。

---

## 快速手动验证

```bash
# Go（8156 为例）
cd go && go run .
curl -i -H 'X-Trace-Id: demo-1' localhost:8156/errors/wrap_chain
curl -i -H 'X-Trace-Id: demo-2' localhost:8156/errors/panic
curl -i localhost:8156/errors/async_detached && sleep 0.5 && curl -s localhost:8156/stats
```
