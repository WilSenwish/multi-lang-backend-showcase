# 场景 12：优雅关闭（Graceful Shutdown）

## 业务描述

**云原生必备场景** — 实现正确的优雅关闭流程：

收到 `SIGTERM`（K8s pod 下线信号）或 `SIGINT`（Ctrl+C）时：
1. **停止接收新请求**（关闭监听器）
2. **等待正在处理的请求完成**（超时保护，如 10s）
3. **释放资源**（DB 连接池、Redis 连接、文件句柄）
4. **结束进程**

> ⚠️ 第 4 步别写成"正常退出 `exit 0`"：进程是被信号叫醒的，运行时在收尾后往往会把信号的
> 默认处置恢复回去，进程最终以 `-15`（SIGTERM）或 `143`（128+15）结束，这是**正常现象**。
> 判断优雅关闭是否成功，要看**日志里的关闭阶段标记**，不要看退出码（详见 §特别关注）。

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
| Python | `loop.add_signal_handler`（配合 `uvicorn.Server.handle_exit`） | lifespan 关闭阶段 + `asyncio.wait_for` 轮询 in-flight | lifespan 的 `yield` 之后（**atexit 不会执行**） |
| Rust | `tokio::signal::ctrl_c()` / `tokio::signal::unix` | `axum::serve().graceful_shutdown()` | Rust Drop trait 自动清理 |
| TS(Node) | `process.on('SIGTERM')` | `server.close()` + 定时器超时 | fastify `.close()` + 自定义清理 |

### 特别关注
- **Java 开发者常见坑**：Spring Boot 默认不处理 SIGTERM，需要配置
- **Go 设计最优雅**：`signal.NotifyContext` + `http.Server.Shutdown` 一行搞定
- **Rust 的 Graceful Shutdown**：axum 原生支持，和 tokio 无缝集成
- **Python 有三个实测坑**（详见 [docs/cloud-native-practice.md](../../docs/cloud-native-practice.md)）：
  1. 信号回调的 `signum` 是 **int**，`sig.name` 会抛 `AttributeError`，要用 `signal.Signals(signum).name`
  2. 只 `asyncio.Event.set()` **不会**让 uvicorn 停下来，必须驱动 `handle_exit` / `should_exit`
  3. 进程最终**被信号终止**，`atexit` 与未 flush 的 stdout 都会丢 → 需要行缓冲或 `python3 -u`
- **K8s 适配**：探针必须在关闭期间保持 ready → 可在 readinessProbe 返回 false
- **别用退出码判定**：Java 在 `mvn spring-boot:run` 下会打印
  `[ERROR] ... Process terminated with exit code: 143`，这是包装进程看到子进程被 SIGTERM 结束后的
  正常抱怨，不代表优雅关闭失败

---

## 关键对比

| 维度 | Java | Go | Python | Rust | TS(Node) |
|------|------|----|--------|------|----------|
| **端口** | 8130 | 8131 | 8132 | 8133 | 8134 |
| **信号捕获** | ContextClosedEvent + shutdown hook | signal.NotifyContext（一行） | loop.add_signal_handler + asyncio.Event（经 uvicorn handle_exit 真正退出） | tokio::signal::unix + graceful_shutdown | process.on('SIGTERM') |
| **停止接收** | Spring Boot 自动（Tomcat close） | http.Server.Shutdown()（自动关闭 listener） | FastAPI/uvicorn 自动 | axum Serve.graceful_shutdown | fastify.close() |
| **等待机制** | 轮询 CountDownLatch + 超时 | server.Shutdown(ctx) 自动等待 | asyncio.wait_for + 轮询 | 手动循环 + axum 等待 in-flight | fastify.close() 等待 |
| **超时保护** | ✅ 10s 超时强制关闭 | ✅ context.WithTimeout(10s) | ✅ uvicorn timeout_graceful_shutdown=10 | ✅ 10s 手动超时循环 | ✅ setTimeout + process.exit |
| **资源释放** | Spring Bean 自动清理（SmartLifecycle） | defer server.Close() + defer stop() | FastAPI lifespan（yield 之后）；atexit 不执行 | Rust Drop trait + tokio spawn 任务 | fastify.close() + process.exit |
| **K8s readinessProbe** | 返回 503（shutting_down 时） | 返回 503 | 返回 503 | 返回 503 | 返回 503 |
| **代码行数** | ~150 行（Application + Controller + ShutdownConfig） | ~120 行（**Go 最简洁**） | ~140 行 | ~150 行 | ~140 行 |
| **设计优雅度** | ⭐⭐⭐（Spring 自动处理但啰嗦） | ⭐⭐⭐⭐⭐（几行搞定） | ⭐⭐⭐⭐（asyncio 自然） | ⭐⭐⭐⭐⭐（axum 原生支持） | ⭐⭐⭐⭐（close 自动等待） |
| **优势** | Spring Boot 自动管理 Bean 生命周期 | **signal.NotifyContext + Shutdown 一行搞定** | asyncio 自然、FastAPI lifespan 好用 | axum graceful_shutdown 原生 + tokio 信号 | fastify.close() 自动等待 + 单线程简单 |
| **痛点 & 坑** | Spring Boot 2.1.x 默认不优雅、要自己配；`mvn spring-boot:run` 会报 exit code 143（正常） | server.Close() 和 Shutdown 冲突（只用 Shutdown） | 信号回调是 int 不是枚举；只 set() 事件不会退出；atexit / 未 flush 的 stdout 会丢 | tokio::signal::unix 只在 unix 可用 | process.exit 强制、超时保护必须有 |

---

## 统一测试命令

```bash
# 启动后发送信号测试优雅关闭
# 步骤：
# 1. 启动一个服务（例如 Go）
# 2. 另一个终端打一个耗时请求：curl http://localhost:8131/api/long-task
# 3. 主终端 kill -TERM <pid>
# 4. 观察日志：应该等待 long-task 完成后再退出

# 逐个测试（每个语言都一样流程）
# Java
mise exec -- mvn spring-boot:run -q  # 在 scenarios/12-graceful-shutdown/java
kill -TERM $(pgrep -f SpringBoot)

# Go
go run main.go  # 在 scenarios/12-graceful-shutdown/go
kill -TERM $(pgrep -f graceful-shutdown)

# Python
python3 main.py  # 在 scenarios/12-graceful-shutdown/python
# 若把输出重定向到文件，加 -u（或 PYTHONUNBUFFERED=1）：进程最终会被信号终止，
# 未 flush 的缓冲会整块丢失，日志里就看不到关闭过程了
kill -TERM $(pgrep -f "python3 main")

# Rust
cargo run  # 在 scenarios/12-graceful-shutdown/rust
kill -TERM $(pgrep -f "graceful-shutdown")

# TS-Node
npm run dev  # 在 scenarios/12-graceful-shutdown/ts-node
kill -TERM $(pgrep -f "tsx")
```

### 预期日志输出（Go 示例）

```
[Go] server starting on :8131
[REQUEST] 开始处理 long-task, id=1, in-flight=1
========================================
[GRACEFUL SHUTDOWN] received signal: context canceled
[GRACEFUL SHUTDOWN] Step 1/4: 标记 shutting_down=true
[GRACEFUL SHUTDOWN] Step 2/4: 停止接收新请求
[GRACEFUL SHUTDOWN] Step 3/4: 等待 in-flight 请求完成 (timeout=10s)
[REQUEST] 完成 long-task, id=1
[GRACEFUL SHUTDOWN] ✅ Shutdown 成功，所有请求完成
[GRACEFUL SHUTDOWN] Step 4/4: 释放资源
[GRACEFUL SHUTDOWN] ✅ Shutdown complete
========================================
```

---

## 运行方式

### Java (端口 8130)
```bash
cd scenarios/12-graceful-shutdown/java
mise exec -- mvn spring-boot:run
kill -TERM $(pgrep -f graceful-shutdown)
```

### Go (端口 8131)
```bash
cd scenarios/12-graceful-shutdown/go
go run main.go
kill -TERM $(pgrep -f grace)
```

### Python (端口 8132)
```bash
cd scenarios/12-graceful-shutdown/python
pip install -r requirements.txt
python3 -u main.py          # -u 保证关闭过程日志不被缓冲吞掉
kill -TERM $(pgrep -f "python3 main")
```

### Rust (端口 8133)
```bash
cd scenarios/12-graceful-shutdown/rust
cargo run
kill -TERM $(pgrep -f graceful-shutdown)
```

### TS(Node) (端口 8134)
```bash
cd scenarios/12-graceful-shutdown/ts-node
npm install && npm run dev
kill -TERM $(pgrep -f tsx)
```

---

## 选型思考

### 五种优雅关闭实现定位

| 场景 | 推荐 | 原因 |
|------|------|------|
| **Java/Spring Boot** | ★ Spring Boot 自动 + SmartLifecycle | Spring 自动管理 Bean 生命周期，优雅关闭是内置能力 |
| **Go 微服务** | 🐹 **signal.NotifyContext + Shutdown** | Go 设计最简洁优雅，几行搞定 |
| **Python async 服务** | 🐍 FastAPI lifespan + uvicorn timeout | FastAPI lifespan 自然、uvicorn 内置关闭 |
| **Rust 高性能** | 🦀 axum graceful_shutdown + tokio::signal | axum 原生支持 + tokio 信号 |
| **Node/BFF** | 🟦 fastify.close() | close() 自动等待 + 单线程无锁简单 |

### 关键选型决策点

| 问题 | 答案 |
|------|------|
| **设计最优雅？** | 🐹 Go signal.NotifyContext（一行搞定） |
| **必须要超时保护吗？** | **必须！** 不然死等不完 → 进程永远不退出 → K8s 强制 SIGKILL（数据可能丢） |
| **K8s terminationGracePeriodSeconds？** | 默认 30s，必须在这个时间内完成关闭（建议设置关闭超时 10-20s） |
| **readinessProbe 怎么处理？** | 关闭期间返回 503 → K8s 立即把 pod 从 endpoint 移除 → 不再接收新流量 |
| **资源释放顺序？** | 停接收请求 → 等 in-flight 完成 → 关 DB 连接池 → 关 Redis → 清理临时文件 → 结束进程（退出码常为 -15/143，别拿它当判据） |

