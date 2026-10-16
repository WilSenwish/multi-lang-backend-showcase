# 云原生工程实践

> 优雅关闭、容器信号处理、Docker 多阶段构建、健康检查 — 生产环境必备的工程细节。

---

## 1. 优雅关闭（Graceful Shutdown）

### 需求
收到 `SIGINT` / `SIGTERM` 信号时：
1. 停止接收新请求
2. 等待正在处理的请求完成（超时保护）
3. 关闭连接池、文件句柄等资源
4. 结束进程

> ⚠️ 注意第 4 点：**不要用「退出码是否为 0」判断优雅关闭是否成功**。
> 进程是被信号"叫醒"的，许多运行时在关闭收尾后会把信号的默认处置恢复回去，
> 于是进程最终以 `-15`（SIGTERM）/ `143`（128+15）结束 —— 这是正常现象。
> 可靠判据是**日志里的关闭阶段标记**（例如 `Shutdown complete`），本仓库的验证脚本即按此判定。

### 各语言实现差异

| 语言 | 信号捕获 | 等待机制 | 资源释放 |
|------|---------|---------|---------|
| Java | `Signal` / Spring `SmartLifecycle` | `CountDownLatch` + 线程池 `shutdown()` | Spring 自动管理 Bean 生命周期 |
| Go | `os.Signal` channel | `http.Server.Shutdown(ctx)` + WaitGroup | defer + Close() |
| Python | `loop.add_signal_handler` + `uvicorn.Server.handle_exit` | lifespan 关闭阶段 + `asyncio.wait_for` 超时保护 | lifespan 的 `yield` 之后（**别指望 atexit**，见下方坑 3） |
| Rust | `tokio::signal` + `ctrlc` | `axum::serve().graceful_shutdown()` | Drop trait 自动清理 |
| TS(Node) | `process.on('SIGTERM')` | `server.close()` + 定时器超时 | fastify `.close()` |

### Java 开发者常见坑
- Spring Boot 默认不处理 SIGTERM，需要配置
- Tomcat 线程池关闭超时默认 30s，K8s terminationGracePeriodSeconds 要匹配

### Python 优雅关闭的三个坑（实测）

这三个坑都会让"看起来很优雅"的关闭实际跑不通，或者让验证结论失真：

1. **信号回调收到的 `signum` 是 `int`，不是 `signal.Signals`**。
   写 `sig.name` 会抛 `AttributeError: 'int' object has no attribute 'name'`；
   要用 `signal.Signals(signum).name` 才能拿到 `'SIGTERM'` 这样的名字。

2. **只 `asyncio.Event.set()` 不会让服务停下来**。
   信号处理器里 set 一个事件只是"通知"，进程仍会继续 accept 新连接；
   必须同时驱动框架的关闭流程（uvicorn：`SERVER.handle_exit(signum, frame)`，
   其内部即置 `should_exit = True`；重复信号则强退），否则只能等外部 SIGKILL —— 优雅关闭是假的。

3. **进程最终"被信号终止"，`atexit` 与未 flush 的 stdout 都会丢**。
   实测 uvicorn 在完成 graceful shutdown 后进程以 `-15` / `1` 结束，
   Python 解释器的正常收尾（`atexit`、缓冲区 flush）**不执行**：

   ```
   $ kill -TERM <pid>          # 进程 returncode = -15，atexit 从未触发
   # 如果 stdout 重定向到文件（块缓冲），应用自己 print 的日志会整块消失
   ```

   两个应对方式（本仓库同时用了）：
   - 应用侧开行缓冲：`sys.stdout.reconfigure(line_buffering=True)`（`main.py` 顶部）
   - 验证/运行侧：`python3 -u` 或 `PYTHONUNBUFFERED=1`

   > 这一条也解释了为什么 Java 场景在 `mvn spring-boot:run` 下会打印
   > `[ERROR] Process terminated with exit code: 143` —— 那是 Maven 包装进程看到
   > 子进程被 SIGTERM 结束后的正常抱怨，不是优雅关闭失败。

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
