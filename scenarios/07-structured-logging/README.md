# 场景 07：结构化日志

## 业务描述

统一实现 JSON 结构化日志输出，支持：

- **日志级别**：TRACE / DEBUG / INFO / WARN / ERROR
- **结构化字段**：业务字段（userId、requestId、costMs 等）
- **错误栈**：异常堆栈正确输出
- **滚动切割**：按大小/时间滚动
- **stdout 输出**：云原生最佳实践（直接输出到 stdout，由容器收集）

### 统一输出格式

```json
{"level":"INFO","time":"2026-10-14T10:00:00.123Z","caller":"main.go:42","msg":"request handled","requestId":"abc-123","userId":42,"costMs":15}
```

所有语言实现**日志格式和级别语义完全一致**。

---

## 契约要点（验证器按这些命题断言）

契约分两层。**HTTP 层**：响应键名一致；`request_id` 必须是 **8 位十六进制**；
`/bench` 的 `count` 缺省 1000，非数字 / `< 1` → **400**；方法不匹配 → **405**。
**日志层**：每个端点的应用日志必须带齐下表字段（级别、消息、链路字段、业务字段），
ERROR 行必须带错误栈。字段路径**逐语言声明**（库命名差异不抹平，语义字段必须齐全）：

| 语义字段 | Java | Go | Python | Rust | TS(Node) |
|---------|------|----|--------|------|----------|
| 级别（info） | `"INFO"` | `"info"` | `"info"` | `"INFO"` | `30` |
| 级别（error） | `"ERROR"` | `"error"` | `"error"` | `"ERROR"` | `50` |
| 消息 | `message` | `msg` | `event` | `fields.message` | `msg` |
| requestId | `requestId` | `requestId` | `requestId` | `span.requestId` | `reqId` |
| userId | `userId` | `userId` | `userId` | `span.userId` | `userId` |
| path | `path` | `path` | `path` | `span.path` | `path` |
| costMs | `costMs` | `costMs` | `costMs` | `fields.costMs` | `costMs` |
| 错误栈 | `stack_trace` | `stacktrace` | `exception` | `fields.error` | `err.stack` |

逐端点断言：`/ping` → `pong` + 两条 INFO（`ping request handled` / `request completed`，后者带 `costMs`）；
`/debug` → INFO `debug endpoint hit`（`userId=debug-user`）；`/error` → ERROR
`request failed with exception`（`costMs=150`、`errorCode=NULL_POINTER`、错误栈非空）；
`/bench?count=N` → 恰好 **N 条** `benchmark log entry` + 一条 `benchmark completed`
（`count`/`totalCostMs`/`avgLogNs` 均为非负数字）——**条数是"日志真的逐条落盘"的硬证据**。

> **踩过的坑（均已修复，详见 VERIFICATION.md §12 批次 3）**：
> Java 的 SLF4J kv 参数会被 logstash encoder 整个丢弃（必须用 `StructuredArguments.kv`）；
> zap 生产配置默认开启采样（1000 条 bench 只落盘 ~109 条）；
> fastify 的 `loggerInstance` 选项不存在（传错键名会被静默忽略）；
> structlog 的 threadlocal 不配 `merge_threadlocal` processor 时链路字段永远不进日志；
> Spring Boot 的 `BasicErrorController` 默认也注册在 `/error`（会把 POST 接走返回 500）。

---

## 实现清单

| 语言 | 日志库 | 特点 |
|------|--------|------|
| Java | SLF4J + Logback | 重量级，XML 配置，社区成熟 |
| Go | `slog`（标准库，Go 1.21+） / zap | slog 统一 API，zap 零分配 |
| Python | structlog | 结构化友好，链式 API |
| Rust | tracing | 编译期字段约束，性能极致 |
| TS(Node) | pino | 极快（异步），JSON 原生 |

### 特别关注
- **性能开销**：是否零分配（zap / tracing / pino 是）
- **容器环境适配**：直接 stdout → kubectl logs 可看
- **错误栈格式**：异常堆栈如何嵌入 JSON

---

## 关键对比

| 维度 | Java | Go | Python | Rust | TS(Node) |
|------|------|----|--------|------|----------|
| **端口** | 8105 | 8106 | 8107 | 8108 | 8109 |
| **日志 API / 实现** | SLF4J + Logback | zap (uber-go/zap) | structlog | tracing + tracing-subscriber | pino |
| **JSON 输出** | logstash-logback-encoder | zap 内置 JSON encoder | structlog JSONRenderer | tracing-subscriber .json() | pino 内置 JSON |
| **零分配** | ❌ Logback 有开销 | ✅ zap 零分配 | ❌ Python 循环天生有开销 | ✅ tracing 编译期宏 | ✅ pino 异步零分配 |
| **异步写入** | ❌ Logback 同步（AsyncAppender 可选） | ❌ zap 默认同步，高吞吐够用 | ❌ structlog 同步 | ❌ tracing 默认同步 | ✅ pino 异步写入队列 |
| **时间戳格式** | ISO-8601（logback encoder） | zapcore.ISO8601 | structlog TimeStamper(fmt="iso") | tracing-subscriber 自动 ISO | pino stdTimeFunctions.isoTime |
| **Caller 信息** | ✅ IncludeCallerData=true | ✅ AddCaller 字段 | ✅ CallsiteParameterAdder | ✅ .with_file + .with_line_number | ❌ 默认无（pino caller 需额外） |
| **Request 级字段传递** | ⭐⭐⭐⭐⭐ MDC（自动，全链路透传） | ⭐⭐⭐ context.Context 手动传 | ⭐⭐⭐ contextvars 手动传 | ⭐⭐⭐⭐⭐ span.enter() 自动继承 | ⭐⭐⭐⭐ fastify request.log 自动带 reqId |
| **错误栈嵌入 JSON** | ✅ Logback 自动把 Throwable 嵌入 stack_trace | ✅ zap.Error(err) + zap.Stack() | ✅ exc_info=True 自动渲染 traceback | ✅ tracing error=(% ?e) 嵌入 | ✅ pino 自动识别 Error，输出 stack |
| **日志级别控制** | logback-spring.xml 配置 | zap 生产配置过滤 Debug | structlog min_level | EnvFilter：RUST_LOG=debug | pino level 配置 |
| **滚动切割** | ✅ logback RollingFileAppender | ❌ 不内置（用 lumberjack） | ❌ 不内置 | ❌ 不内置 | ❌ 不内置（用 pino-roll / rotation） |
| **容器适配（stdout）** | ✅ 推荐，别配 FILE appender | ✅ stdout / stderr | ✅ PrintLoggerFactory → stdout | ✅ stdout | ✅ stdout |
| **性能排序** | 3️⃣ Logback 中等 | 1️⃣ zap 极快 | 5️⃣ structlog 慢（Python） | 1️⃣ tracing 极快 | 2️⃣ pino 极快 |
| **优势** | MDC 自动透传、Spring 无缝 | 零分配、极简、并发安全 | processor 链灵活 | Span 嵌套 + 编译期字段 | 异步 + fastify 无缝 |
| **痛点 & 坑** | XML 配置啰嗦、JVM 冷启动 | context 手动传字段（无自动 MDC） | Python 慢、processor 链 debug 难 | 宏复杂、EnvFilter 语法啰嗦 | caller 默认无、同步写慢用 pino-async |

---

## 运行方式

### Java (端口 8105)
```bash
cd scenarios/07-structured-logging/java
mise exec -- mvn spring-boot:run
```

### Go (端口 8106)
```bash
cd scenarios/07-structured-logging/go
go mod tidy   # 首次下载 zap
go run main.go
```

### Python (端口 8107)
```bash
cd scenarios/07-structured-logging/python
pip install -r requirements.txt
python main.py
```

### Rust (端口 8108)
```bash
cd scenarios/07-structured-logging/rust
cargo run
# Debug 级别
RUST_LOG=debug cargo run
```

### TS(Node) (端口 8109)
```bash
cd scenarios/07-structured-logging/ts-node
npm install && npm run dev
```

### 批量测试
```bash
# 统一测试（每个端点各打一条日志）
echo "=== 结构化日志测试 ==="
for port in 8105 8106 8107 8108 8109; do
  echo ""
  echo "--- Port $port (/ping) ---"
  curl -s http://localhost:$port/ping | jq -c .
  echo "--- Port $port (/error) ---"
  curl -s http://localhost:$port/error | jq -c .
  echo "--- Port $port (/bench?count=100) ---"
  curl -s "http://localhost:$port/bench?count=100" | jq -c .
done

# 观察：每个进程的 stdout 应该输出 JSON 结构化日志
# 用 jq 过滤查看特定字段：
# curl -s http://localhost:8105/ping > /dev/null 2>&1 ; echo "stdout 应该有 JSON"
```

---

## 统一 JSON 输出格式（5 语言对比）

### Java (Logback JSON)
```json
{"@timestamp":"2026-10-15T10:00:00.123+08:00","level":"INFO","thread":"main","logger":"c.s.l.LoggingController","message":"ping request handled","requestId":"abc123","userId":"anonymous","path":"/ping","costMs":5}
```

### Go (zap)
```json
{"level":"info","ts":1729000000.123,"caller":"main.go:42","msg":"ping request handled","requestId":"abc123","userId":"anonymous","path":"/ping"}
```

### Python (structlog)
```json
{"event":"ping request handled","level":"info","timestamp":"2026-10-15T02:00:00.123345Z","requestId":"abc123","userId":"anonymous","path":"/ping"}
```

### Rust (tracing)
```json
{"level":"INFO","target":"structured_logging","fields.message":"ping request handled","requestId":"abc123","userId":"anonymous","path":"/ping","t":"2026-10-15T02:00:00.123456Z"}
```

### TS(Node) (pino)
```json
{"level":30,"time":1729000000123,"pid":12345,"hostname":"macbook.local","req":{"id":"abc123","method":"GET","url":"/ping"},"msg":"ping request handled","requestId":"abc123","userId":"anonymous"}
```

---

## 选型思考

### 五种日志库定位

| 场景 | 推荐 | 原因 |
|------|------|------|
| **Java/Spring Boot 项目** | ☕ Logback + logstash-logback-encoder | MDC 自动透传，XML 配置 + profile 分环境，社区成熟 |
| **Go 微服务 / 云原生** | 🐹 zap (SugaredLogger) | 零分配极快，JSON encoder 开箱即用，和 Go 生态无缝 |
| **Python 项目** | 🐍 structlog | processor 链灵活，链式 API 好用，比原生 logging 强很多 |
| **Rust 项目 / 高性能服务** | 🦀 tracing + tracing-subscriber | 编译期字段检查，Span 嵌套 + 可视化，tracing-otel 对接 OpenTelemetry |
| **Node / BFF 层** | 🟦 pino | 异步极快，fastify 无缝集成，pino-pretty 开发体验好 |

### 关键选型决策点

| 问题 | 答案 |
|------|------|
| **需要自动传递 requestId（链路追踪）？** | Java MDC 最方便 → Rust span.enter() 次之 → Go/Python/Node 要手动 context |
| **性能敏感（每秒几十万条）？** | zap = tracing = pino >> Logback >> structlog |
| **日志写到哪里？** | **云原生：stdout（容器收集）** / 磁盘：zapcore/lumberjack / 外部：Loki/ELK |
| **需要滚动切割？** | Logback 内置最强，其他语言要外接库 |
| **统一跨语言格式？** | 都输出 JSON（字段名可以统一约定），用 OpenTelemetry 标准 |
| **调试时想美化？** | Java/Golangback XML 配 pattern、zap/zapcore.ConsoleEncoder、pino-pretty |

