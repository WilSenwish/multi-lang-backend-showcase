# 场景 02：并发任务处理 ⭐⭐

## 业务描述

**本仓库最核心场景** — 统一需求：**并发处理 100 个任务**（模拟外部 HTTP 请求，每个耗时 100ms），对比五门语言的并发模型本质差异。

### 统一接口

```bash
# 启动服务后，发送触发请求
POST /run
Content-Type: application/json

{
  "task_count": 100,        # 任务总数
  "task_delay_ms": 100,    # 每个任务模拟耗时（IO 密集，sleep）
  "concurrency": 10        # ⭐ 同时最多执行的任务数（公平对比关键！）
}

# 响应
{
  "total_tasks": 100,
  "concurrency": 10,
  "total_time_ms": 1100,       # 总耗时（越小越好）
  "throughput": 90.9,          # 每秒处理数 = task_count / (total_time_ms/1000)
  "task_delay_ms": 100,
  "results": [
    {"id": 0, "status": "ok", "duration_ms": 102},
    {"id": 1, "status": "ok", "duration_ms": 98},
    ...
  ]
}
```

### 为什么必须有 `concurrency` 参数？

| 没有它 | 有了它 |
|--------|--------|
| Go 直接 100 goroutine 全开 | Go 用 buffered channel 限流到 10 |
| Java 线程池可能只有 10 线程 | Java 用固定 10 线程 ThreadPoolExecutor |
| Python asyncio gather 100 协程 | asyncio.Semaphore(10) |
| **对比不公平**（各自按自己的最大并发跑） | **对比公平**（都限到同样的并发数） |

> **核心设计**：`concurrency` 参数本身就是对比点 — 每个语言用不同的原语实现限流（线程池 / channel / Semaphore / 信号量 / Promise 队列）。

### 任务类型：IO 密集

每个任务的工作：**sleep 指定毫秒数**（模拟外部 HTTP 请求等待），不做 CPU 计算。这样 async 模型（Python asyncio / TS 事件循环 / Rust tokio）才能发挥优势。

### 核心对比指标
- **总耗时**（越少越好：理想值 = ceil(task_count / concurrency) × task_delay_ms）
- **吞吐量**（tasks/sec）
- **代码复杂度**（实现同功能的代码量和心智负担）

所有语言实现**业务逻辑完全一致**。

---

## 实现清单

| 语言 | 并发方案 | 限流原语 | 框架 |
|------|---------|---------|------|
| Java | `CompletableFuture` + 固定线程池 | `Executors.newFixedThreadPool(concurrency)` | Spring Boot Web |
| Go | `goroutine` + `sync.WaitGroup` | **buffered channel**（容量=concurrency） | 标准库 `net/http` |
| Python | `asyncio` + `asyncio.gather()` | **`asyncio.Semaphore(concurrency)`** | FastAPI + uvicorn |
| Rust | `tokio` 多线程 + `JoinHandle` | **`tokio::Semaphore(concurrency)`** | axum |
| TS(Node) | `Promise.all` + `async-await` | **手写 p-limit 队列** | fastify |

### 特别关注

- Python 的 **GIL 影响**：asyncio 能高效处理 IO 密集，但 CPU 密集受 GIL 阻塞
- Go **Goroutine**：极轻量（2KB 栈），百万级轻松
- Rust **编译期防竞态**：所有权系统从根源禁止数据竞争
- Java **线程池调优**：默认 Tomcat 10-200 线程
- TS(Node) **单线程事件循环**：IO 极高效，天然避免竞争

---

## 关键对比

| 维度 | Java | Go | Python | Rust | TS(Node) |
|------|------|----|--------|------|----------|
| **端口** | 8085 | 8086 | 8087 | 8088 | 8089 |
| **线程模型** | 1:1 平台线程 | M:N Goroutine | GIL + asyncio 协程 | 原生线程 + tokio 异步 | 单线程事件循环 |
| **并发限流原语** | `Executors.newFixedThreadPool(N)` | `make(chan struct{}, N)` | `asyncio.Semaphore(N)` | `tokio::Semaphore(N)` | 手写 p-limit |
| **创建成本** | 高（~1MB/线程） | 极低（~2KB/goroutine） | 极低（协程） | 中（原生线程） | 极低（Promise） |
| **CPU 密集** | 多线程并行 | 多核心并行 | **GIL 阻塞** | 多线程并行 | 需 worker_threads |
| **IO 密集** | 线程池上限阻塞 | 百万级 goroutine | asyncio 单线程调度 | tokio 多线程调度 | 事件循环调度 |
| **数据竞争** | 需锁保护 | channel 避免共享 | GIL 天然避免 | **编译期禁止** | 单线程避免 |
| **同步/异步** | 阻塞式 Thread.sleep | 阻塞式 time.Sleep | **非阻塞 await sleep** | **非阻塞 .await sleep** | **非阻塞 setTimeout** |
| **代码行数(≈)** | ~110 行 | ~120 行 | ~90 行 | ~130 行 | ~120 行（含 p-limit） |
| **吞吐量** | 📊 待压测 | 📊 待压测 | 📊 待压测 | 📊 待压测 | 📊 待压测 |
| **总耗时** | 📊 待压测 | 📊 待压测 | 📊 待压测 | 📊 待压测 | 📊 待压测 |
| **优势** | 生态全，和现有 Java 无缝集成 | 极简，goroutine 好用，channel 优雅 | asyncio + FastAPI 开发爽，类型安全 | 编译期安全，零 GC，极致性能 | 零阻塞，单线程无竞争 |
| **痛点 & 坑** | Thread.sleep 阻塞线程，线程池用完要关 | 别忘了 WaitGroup.Done()，channel 用完要关闭 | GIL CPU 密集无效，asyncio 异常传播坑 | Arc<Mutex> 在线程间传数据，生命周期标注 | 单线程 CPU 密集会阻塞整个循环 |

---

## 运行方式

### Java (端口 8085)
```bash
cd scenarios/02-concurrent-task/java
mvn spring-boot:run
# 测试
curl -s -X POST http://localhost:8085/run \
  -H 'Content-Type: application/json' \
  -d '{"task_count":100,"task_delay_ms":100,"concurrency":10}' | jq '.total_time_ms'
```

### Go (端口 8086)
```bash
cd scenarios/02-concurrent-task/go
go run main.go
# 测试
curl -s -X POST http://localhost:8086/run \
  -H 'Content-Type: application/json' \
  -d '{"task_count":100,"task_delay_ms":100,"concurrency":10}' | jq '.total_time_ms'
```

### Python (端口 8087)
```bash
cd scenarios/02-concurrent-task/python
pip install -r requirements.txt
uvicorn main:app --port 8087
# 测试
curl -s -X POST http://localhost:8087/run \
  -H 'Content-Type: application/json' \
  -d '{"task_count":100,"task_delay_ms":100,"concurrency":10}' | jq '.total_time_ms'
```

### Rust (端口 8088)
```bash
cd scenarios/02-concurrent-task/rust
cargo run
# 测试
curl -s -X POST http://localhost:8088/run \
  -H 'Content-Type: application/json' \
  -d '{"task_count":100,"task_delay_ms":100,"concurrency":10}' | jq '.total_time_ms'
```

### TS(Node) (端口 8089)
```bash
cd scenarios/02-concurrent-task/ts-node
npm install && npm run dev
# 测试
curl -s -X POST http://localhost:8089/run \
  -H 'Content-Type: application/json' \
  -d '{"task_count":100,"task_delay_ms":100,"concurrency":10}' | jq '.total_time_ms'
```

### 批量测试（所有服务都启动后）
```bash
# 理想值：ceil(100/10) × 100ms = 1000ms
# 因为 sleep 是 IO 密集，所有语言应该都接近这个值
for port in 8085 8086 8087 8088 8089; do
  echo "=== port $port ==="
  curl -s -X POST http://localhost:$port/run \
    -H 'Content-Type: application/json' \
    -d '{"task_count":100,"task_delay_ms":100,"concurrency":10}' | jq '{total_time_ms, throughput}'
done
```

---

## 选型思考

<!-- TODO: 实现后补充选型建议 -->

