# 云原生工程实践

> 优雅关闭、容器信号处理、Docker 多阶段构建、健康检查 — 生产环境必备的工程细节。

---

## 1. 优雅关闭（Graceful Shutdown）

### 需求
收到 `SIGINT` / `SIGTERM` 信号时：
1. 停止接收新请求
2. 等待正在处理的请求完成（超时保护）
3. 关闭连接池、文件句柄等资源
4. 正常退出（`exit 0`）

### 各语言实现差异

| 语言 | 信号捕获 | 等待机制 | 资源释放 |
|------|---------|---------|---------|
| Java | `Signal` / Spring `SmartLifecycle` | `CountDownLatch` + 线程池 `shutdown()` | Spring 自动管理 Bean 生命周期 |
| Go | `os.Signal` channel | `http.Server.Shutdown(ctx)` + WaitGroup | defer + Close() |
| Python | `signal` 模块 + asyncio | `asyncio.run_until_complete()` 清理 | try-finally + atexit |
| Rust | `tokio::signal` + `ctrlc` | `axum::serve().graceful_shutdown()` | Drop trait 自动清理 |
| TS(Node) | `process.on('SIGTERM')` | `server.close()` + 定时器超时 | fastify `.close()` |

### Java 开发者常见坑
- Spring Boot 默认不处理 SIGTERM，需要配置
- Tomcat 线程池关闭超时默认 30s，K8s terminationGracePeriodSeconds 要匹配

---

## 2. Docker 多阶段构建

### Go / Rust（极简）
```dockerfile
# Go
FROM golang:1.22 AS builder
WORKDIR /app
COPY . .
RUN CGO_ENABLED=0 go build -o /out/app

FROM scratch
COPY --from=builder /out/app /app
EXPOSE 8081
ENTRYPOINT ["/app"]
```

- 最终镜像只有二进制 + CA 证书（~10MB）
- 完全无运行时依赖

### Java（推荐 Native Image）
```dockerfile
FROM eclipse-temurin:17-jre-alpine
COPY target/app.jar /app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app.jar"]
```
或 GraalVM Native Image → 编译成原生二进制（类似 Go/Rust）

### Python / TS
- 需要包含运行时，镜像较大
- slim 基础镜像 + 合并 RUN 减小层

---

## 3. 健康检查（Health Check）

| 语言 | 框架支持 | K8s 探针 |
|------|---------|---------|
| Java | Spring Boot Actuator `/actuator/health` | liveness + readiness |
| Go | 手写 `/health` endpoint 或 healthz 库 | liveness + readiness |
| Python | FastAPI `/health` 或 `fastapi-health` | |
| Rust | axum `/health` route | |
| TS(Node) | fastify `@fastify/health` | |

### K8s 探针配置建议
- **livenessProbe**：存活检查，失败则重启容器 → `/health/live`
- **readinessProbe**：就绪检查，失败则从 Service 摘除 → `/health/ready`（含 DB 连接检查）
- **startupProbe**：启动探针（Java 冷启动需要较长初始延迟）

---

## 4. 容器化最佳实践清单

- [ ] 使用 `.dockerignore` 排除无关文件
- [ ] 多阶段构建，最小化最终镜像
- [ ] 非 root 用户运行容器
- [ ] 结构化日志输出到 stdout/stderr
- [ ] 实现 `/health` / `/ready` 端点
- [ ] 正确处理 SIGTERM，优雅关闭
- [ ] 配置合理的资源 requests/limits
- [ ] 使用 distroless 或 alpine 基础镜像（如适用）
