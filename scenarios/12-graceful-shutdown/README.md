# 场景 12：优雅关闭（Graceful Shutdown）

## 业务描述

**云原生必备场景** — 实现正确的优雅关闭流程：

收到 `SIGTERM`（K8s pod 下线信号）或 `SIGINT`（Ctrl+C）时：
1. **停止接收新请求**（关闭监听器）
2. **等待正在处理的请求完成**（超时保护，如 10s）
3. **释放资源**（DB 连接池、Redis 连接、文件句柄）
4. **清理完成后正常退出**（`exit 0`）

### 测试方式
```bash
# 启动服务后，发送 SIGTERM
kill -TERM <pid>
# 观察日志：
# [INFO] received SIGTERM, starting graceful shutdown...
# [INFO] waiting for in-flight requests (timeout=10s)...
# [INFO] all requests completed, releasing resources...
# [INFO] shutdown complete, exiting
```

> K8s 中 `terminationGracePeriodSeconds` 默认 30s，必须在这个时间内完成关闭。

所有语言实现**业务逻辑完全一致**。

---

## 实现清单

| 语言 | 信号捕获 | 等待机制 | 资源释放 |
|------|---------|---------|---------|
| Java | `Signal` + Spring `SmartLifecycle` | `CountDownLatch` + 线程池 `shutdown()` + `awaitTermination()` | Spring 自动管理 Bean 生命周期 |
| Go | `os.Signal` channel + `signal.NotifyContext` | `http.Server.Shutdown(ctx)` + `sync.WaitGroup` | `defer xxx.Close()` |
| Python | `signal` 模块 + `asyncio.Event` | `asyncio.run_until_complete()` 清理协程 | `try-finally` + `atexit` + async context manager |
| Rust | `tokio::signal::ctrl_c()` / `tokio::signal::unix` | `axum::serve().graceful_shutdown()` | Rust Drop trait 自动清理 |
| TS(Node) | `process.on('SIGTERM')` | `server.close()` + 定时器超时 | fastify `.close()` + 自定义清理 |

### 特别关注
- **Java 开发者常见坑**：Spring Boot 默认不处理 SIGTERM，需要配置
- **Go 设计最优雅**：`signal.NotifyContext` + `http.Server.Shutdown` 一行搞定
- **Rust 的 Graceful Shutdown**：axum 原生支持，和 tokio 无缝集成
- **K8s 适配**：探针必须在关闭期间保持 ready → 可在 readinessProbe 返回 false

---

## 关键对比

| 维度 | Java | Go | Python | Rust | TS(Node) |
|------|------|----|--------|------|----------|
| **信号捕获** | | | | | |
| **等待机制** | | | | | |
| **超时保护** | | | | | |
| **资源释放** | | | | | |
| **K8s 适配** | | | | | |
| **优势** | | | | | |
| **痛点 & 坑** | | | | | |

---

## 运行方式

<!-- TODO: 实现后补充启动/运行命令 -->

### Java
```bash
# TODO
kill -TERM <java_pid>
```

### Go
```bash
# TODO
kill -TERM <go_pid>
```

### Python
```bash
# TODO
kill -TERM <python_pid>
```

### Rust
```bash
# TODO
kill -TERM <rust_pid>
```

### TS(Node)
```bash
# TODO
kill -TERM <node_pid>
```

---

## 选型思考

<!-- TODO: 实现后补充选型建议 -->

