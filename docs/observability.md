# 可观测性专题：日志 / Metrics / Trace

> 云原生时代的三大支柱。五门语言在结构化日志、指标埋点、链路追踪上的生态和实现差异。

---

## 1. 结构化日志（Logging）

| 语言 | 主流库 | 特点 | 性能 |
|------|--------|------|------|
| Java | SLF4J + Logback | 重量级配置，XML/Properties | 中（异步 appender 可加速） |
| Go | zap / slog (标准库) | zap 零分配，slog 统一 API | **极高**（零分配） |
| Python | structlog | 结构化友好，灵活链式 | 中（GC 压力） |
| Rust | tracing | 编译期字段约束，无分配 | **极高** |
| TS(Node) | pino / winston | pino 极快，JSON 结构化 | 高（异步写入） |

### 核心对比维度
- 是否零分配
- 异步日志 vs 同步
- JSON 结构化输出（云原生最佳实践：直接 stdout）
- 滚动切割 / 轮转
- 错误栈打印格式

---

## 2. Metrics 指标

| 语言 | 主流库 | Prometheus 导出 |
|------|--------|----------------|
| Java | Micrometer + Prometheus | ✅ Spring Boot Actuator |
| Go | prometheus/client_golang | ✅ 官方客户端 |
| Python | prometheus_client | ✅ 官方客户端 |
| Rust | metrics + metrics-exporter-prometheus | ✅ |
| TS(Node) | prom-client | ✅ |

### 核心对比维度
- Counter / Gauge / Histogram / Summary 支持
- 自动插桩（HTTP 中间件）
- 标签（Label）管理

---

## 3. 链路追踪（Tracing）

| 语言 | 主流库 | 生态 |
|------|--------|------|
| Java | Micrometer Tracing + Brave | Spring Cloud Sleuth 自动埋点 |
| Go | OpenTelemetry / Jaeger | 社区标准 |
| Python | OpenTelemetry / Lightstep | |
| Rust | opentelemetry | 增长中 |
| TS(Node) | OpenTelemetry / Zipkin | |

---

## 4. 选型建议

| 场景 | 推荐 | 原因 |
|------|------|------|
| 云原生容器部署 | zap / slog / pino / tracing | 直接 stdout JSON，容器日志收集友好 |
| Java 企业项目 | SLF4J + Logback + Micrometer | 成熟生态 + Spring 无缝集成 |
| 高性能中间件 | Rust tracing / Go zap | 零分配，不影响主链路性能 |

---

## 5. 在本仓库中的落地点

### 全场景统一日志规范（2026-11-14 升级）

**所有 17 个场景（00~17）的五门语言**，已统一接入生产级结构化日志框架：

| 语言 | 日志框架 | 级别 | 输出 | 配置方式 | 覆盖场景 |
|------|---------|------|------|---------|---------|
| Java | SLF4J + Logback + logstash-logback-encoder | DEBUG | JSON → stdout | `logback-spring.xml` | 16 个（03 CLI 跳过） |
| Go | go.uber.org/zap v1.27.0 | DEBUG | JSON → stdout | `init()` 全局初始化 | 17 个全部 |
| Python | structlog v24.4.0 | DEBUG | JSON → stdout | `_configure_structlog()` | 17 个全部 |
| Rust | tracing + tracing-subscriber | DEBUG | JSON → stdout | `main()` 开头初始化 | 16 个（05 单测跳过） |
| TS(Node) | pino ^9.6.0 | DEBUG | JSON → stdout | `const logger = pino({...})` | 16 个（05 单测跳过） |

> 场景 03-cli-tool（CLI 工具）：只替换错误输出为日志框架，正常 stdout 保留。
> 场景 05-unit-test-mock（纯单测）：无 main，不接入日志。

### 结构化日志专题场景

| 专题 | 对应场景 | 各语言实际选型 |
|------|---------|---------------|
| 结构化日志深度对比 | [`07-structured-logging`](../scenarios/07-structured-logging/README.md) | Java：SLF4J + `logstash-logback-encoder`｜Go：`zap`（含 context 注入 requestId）｜Python：`structlog` + contextvars｜Rust：`tracing` + `tracing-subscriber(json)`｜TS：`pino` |
| 优雅关闭（与可观测性强相关） | [`12-graceful-shutdown`](../scenarios/12-graceful-shutdown/README.md) | 关闭期的 readiness 探针与在途请求处理，见该场景 README |

> 场景 07 的五门语言统一输出 `level` / `msg` 等字段的 JSON 行，可直接用 `jq` 对比结构差异。

### 三条跨语言通用的实践

1. **日志直接写 stdout，不要写文件**。文件日志在容器里意味着要么挂 volume、要么进容器可写层，
   两者都不利于收集；由采集侧（Fluent Bit / Filebeat / Vector）负责落盘与轮转。
2. **日志切割交给平台，不要交给应用**。lumberjack / RotatingFileAppender 那一套是虚拟机时代的做法，
   容器里 stdout 天然由 runtime 接管轮转。
3. **级别要能在运行时调整，而不是只靠改配置重启**。Go zap 的 `AtomicLevel`、Rust `tracing-subscriber`
   的 `env-filter`、Java Logback 的 `jmxConfigurator` 都支持；排查线上问题时这一条能省一次发布。

### 还没实现的部分（Roadmap 之外）

Metrics 与 Tracing 目前**只有调研、没有场景实现**：13 个场景均未引入 Prometheus 埋点或 OpenTelemetry 链路。
原因见 [ROADMAP.md](../ROADMAP.md) 的「不做什么」—— 引入后会显著增加依赖与启动复杂度，偏离"语言对比"这条主线。
