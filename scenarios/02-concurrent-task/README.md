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

### 五门语言的并发模型本质

| 语言 | 并发单位 | 限流原语 | 调度者 | 并行能力 |
|------|---------|---------|--------|---------|
| Java | 平台线程（1:1 映射 OS 线程） | `ThreadPoolExecutor`（固定 10 线程） | OS 抢占式调度 | ✅ 真并行（多核） |
| Go | goroutine（M:N 复用 OS 线程） | buffered channel（容量 10 作信号量） | Go runtime 调度器 | ✅ 真并行（多核） |
| Python | 协程 | `asyncio.Semaphore(10)` | 事件循环（协作式） | ❌ 受 GIL 限制，同一时刻只有 1 个线程跑 Python 字节码 |
| Rust | tokio 任务 | `Semaphore`（`tokio::sync`） | tokio 多线程调度器（work-stealing） | ✅ 真并行（多核） |
| TS(Node) | Promise | 手写 Promise 并发队列 | 事件循环（协作式） | ❌ 单线程（可用 worker_threads 绕开） |

### 关键结论

1. **IO 密集场景下，四门"真并行"语言拉不开差距**。本场景每个任务是 `sleep(100ms)`，瓶颈在等待而不在 CPU，
   理想耗时都是 `ceil(100/10) × 100ms = 1000ms`，实测五门语言都应接近这个值。**这也正是 `concurrency` 参数存在的意义** ——
   不限流的话，Go 会直接开 100 个 goroutine、Python 会 gather 100 个协程，对比就变成了"谁敢开得多"而非"谁的并发模型好"。
2. **Python / Node 的劣势在 CPU 密集，不在 IO 密集**。若把任务换成纯计算（如斐波那契、图像处理），
   GIL 与单线程事件循环会立刻暴露，吞吐被其余三门语言拉开数量级差距。本场景刻意选 IO 密集，是为了公平。
3. **心智负担排序（个人体感，非基准）**：Go（channel 即限流，最贴合语义）≈ Rust（`Semaphore` + `JoinHandle`，但所有权/生命周期要过关）
   < Java（线程池参数多，需理解队列/拒绝策略）< TS（需手写并发队列，`Promise.all` 本身不限流）< Python（`async` 传染性，一处 await 处处 await）。

### 什么时候选谁

| 场景 | 推荐 | 原因 |
|------|------|------|
| 万级长连接、网关 / 代理 | **Go** / **Rust** | goroutine / tokio 任务内存开销极小，M:N 调度天然适合海量并发 |
| 企业级业务系统，团队规模大 | **Java** | 线程池模型最易被大多数人理解，诊断工具（jstack / Arthas）成熟 |
| IO 密集 + 要快速出活 | **TS(Node)** | 事件循环零心智负担，前后端同构；但别放进 CPU 密集任务 |
| IO 密集 + 数据处理 / AI 编排 | **Python** | asyncio 生态与 AI 库绑定最深，GIL 在纯 IO 场景不构成瓶颈 |
| CPU 密集 + 低延迟 | **Rust** | 无 GC、无运行时抖动，且编译期就挡住数据竞争 |

> ⚠️ 本节的耗时/吞吐为**设计预期值**，实测数据请用上方「批量测试」命令在本机跑出。
> 不同机器、不同 SDK 版本下的绝对值不具备可比性，横向对比应看**相对关系**。

