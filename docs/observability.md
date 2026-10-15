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
