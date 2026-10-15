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
| **日志库** | | | | | |
| **JSON 输出** | | | | | |
| **零分配** | | | | | |
| **异步写入** | | | | | |
| **错误栈** | | | | | |
| **滚动切割** | | | | | |
| **优势** | | | | | |
| **痛点 & 坑** | | | | | |

---

## 运行方式

<!-- TODO: 实现后补充启动/运行命令 -->

### Java
```bash
# TODO
```

### Go
```bash
# TODO
```

### Python
```bash
# TODO
```

### Rust
```bash
# TODO
```

### TS(Node)
```bash
# TODO
```

---

## 选型思考

<!-- TODO: 实现后补充选型建议 -->

