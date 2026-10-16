# 场景 13：CPU 密集并行计算 ⭐

> **边界场景**：本场景刻意选一个"某些语言天生不擅长"的问题，用来回答技术选型里最关键的一问 ——
> **什么时候某门语言根本不该上场，补救方案又要付出多少代价。**

## 业务描述

与场景 02 相同的"并发处理 N 个任务 + `concurrency` 限流"骨架，**只把任务体从 `sleep` 换成纯计算**。

这一个改动就让结论完全反转：场景 02 里五门语言耗时接近（瓶颈是等待），本场景里差距被直接量化。

### 任务体算法（必须跨语言逐位一致）

对每个任务 `id`，以 `id + 1` 为种子跑 `iterations` 次 **uint64 环绕**的线性同余迭代：

```
state = (uint64)(id + 1)
for i in 0..iterations-1:
    state = state * 6364136223846793005 + 1442695040888963407   // mod 2^64
checksum = 无符号十进制(state)
总 checksum = (Σ 各任务 checksum) mod 2^64
```

选这个算法的理由有三条，缺一不可：

1. **纯整数运算** → 没有浮点误差，五门语言的 checksum 可以**逐位比对**（这是能写契约级断言的前提）；
2. **固定的乘加循环** → 编译器无法优化掉，能真实压满 CPU；
3. **要求 64 位无符号环绕** → 顺带把"**TS 没有 64 位整数**"这个语言本质差异逼到台面上（见下文）。

### 统一接口

```bash
POST /compute
Content-Type: application/json

{
  "task_count": 8,          # 任务总数
  "iterations": 2000000,    # 单任务迭代次数（决定单任务耗时量级）
  "concurrency": 4          # ⭐ 同时执行的任务上限，与场景 02 同语义
}

# 响应
{
  "total_tasks": 8,
  "iterations": 2000000,
  "concurrency": 4,
  "cpu_cores": 10,                 # 运行时可见核心数（环境相关，仅参考）
  "total_time_ms": 1234,           # 环境相关，仅参考
  "checksum": "3581735564125982858",   # ⭐ 契约字段：必须与 oracle 一致
  "results": [
    {"id": 0, "checksum": "417981439666351841", "duration_ms": 150},
    ...
  ]
}
```

**字段分两类**（这点很重要，决定了验证器断言什么）：

| 类别 | 字段 | 验证器是否断言 |
|------|------|---------------|
| **契约字段** | `total_tasks`、`iterations`、`concurrency`、`checksum`、`results[].id`、`results[].checksum` | ✅ 必须一致 |
| **环境字段** | `cpu_cores`、`total_time_ms`、`duration_ms` | ❌ 只记录，不断言（受机器/运行时影响） |

### 核心对比指标

- **正确性**（checksum 与 oracle 逐位一致）—— 这是硬门槛
- **耗时**：`concurrency=1` 与 `concurrency=核心数` 的比值 = **实际并行加速比**
- **限流原语的代码量**：同一件事（限制同时运行的任务数），五门语言分别要写多少行

---

## 实现清单

| 语言 | 并行机制 | 限流原语 | 是否真并行 |
|------|---------|---------|-----------|
| Java | 平台线程（1:1 映射 OS 线程） | `Executors.newFixedThreadPool(concurrency)` | ✅ 多核并行 |
| Go | goroutine（M:N 复用 OS 线程） | 带缓冲 `chan struct{}` 当信号量 | ✅ 多核并行 |
| Rust | `std::thread` | `AtomicUsize` 计数器 + `mpsc::channel` | ✅ 多核并行 |
| Python | **进程**（`multiprocessing`） | `ProcessPoolExecutor(max_workers=concurrency)` | ✅ 多核并行（**但必须用进程**） |
| TS(Node) | **Worker 线程** | 手写 Worker 池 + 任务队列 | ✅ 多核并行（**但必须用 worker_threads**） |

### 特别关注：三门语言的"限流原语"成本差异

这是本场景最有选型价值的一张对照：

| 语言 | 实现"最多 N 个任务同时跑"需要什么 | 心智负担 |
|------|--------------------------------|---------|
| **Go** | 一个带缓冲 channel，`sem <- struct{}{}` / `<-sem` | 最低 —— 语言原语直接表达语义 |
| **Rust** | 一个原子计数器 + 一个 channel + `std::thread` | 低 —— 但所有权/生命周期要过关 |
| **Java** | 一个线程池 + `Future` 列表 | 中 —— 参数多，需理解队列与拒绝策略 |
| **TS(Node)** | 手动维护 Worker 数组、空闲派发、完成计数、退出清理 | **高** —— 上述逻辑框架本身不提供 |
| **Python** | `ProcessPoolExecutor` 一行，但要接受进程启动与 pickle 序列化成本 | 中 —— API 简单，代价在别处 |

---

## 关键对比

| 维度 | Java | Go | Python | Rust | TS(Node) |
|------|------|----|--------|------|----------|
| **端口** | 8135 | 8136 | 8137 | 8138 | 8139 |
| **并行单位** | 平台线程 | goroutine | 进程 | OS 线程 | Worker 线程 |
| **64 位整数** | `long`（有符号，补码环绕等价） | `uint64`（原生） | int（任意精度，**须手动 `& MASK`**） | `u64` + `wrapping_*` | ❌ **无，必须 BigInt** |
| **共享内存** | ✅ 线程共享堆 | ✅ goroutine 共享堆 | ❌ 进程间需 pickle | ✅ `Arc` / `Send` 静态检查 | ❌ Worker 是独立 V8 隔离区 |
| **溢出行为** | 静默环绕 | 静默环绕 | 不溢出（须自己截断） | debug panic / release 环绕（**须显式 `wrapping_*` 统一**） | 不溢出（须自己截断） |
| **限流原语代码量** | ~15 行 | ~10 行 | ~5 行（API 简单） | ~20 行 | ~40 行 |
| **启动成本** | 中（JVM 启动 3-10s） | 极低 | 每进程 spawn ~150ms | 低 | 每 worker ~30ms |
| **优势** | 生态成熟、诊断工具齐全 | 原语最贴合语义 | 多进程 API 最省事 | 无 GC、无运行时抖动 | 前端同构、无需额外环境 |
| **痛点 & 坑** | 线程栈 1MB/个，不能无限创建 | 取结果需自己处理切片下标与同步 | GIL 使多线程完全失效，**必须换进程** | debug 构建默认 panic on overflow | 无 64 位整数；Worker 不能共享对象 |

> 实测数据请用下方命令在本机跑出。**不要照抄任何人的跑分** ——
> 绝对值与机器强相关，横向对比应只看**相对关系**（尤其是 `concurrency=1` vs `=核心数` 的加速比）。

---

## 运行方式

### Java（端口 8135）

```bash
cd java
mvn spring-boot:run
```

### Go（端口 8136）

```bash
cd go
export GOPROXY=https://goproxy.cn,direct GOSUMDB=off   # 国内网络建议设置
go run .
```

### Python（端口 8137）

```bash
cd python
pip install -r requirements.txt
python main.py
```

### Rust（端口 8138）

```bash
cd rust
cargo run --release     # ⚠️ 必须 --release：debug 构建的 CPU 计算慢一个数量级，跑分无效
```

### TS(Node)（端口 8139）

```bash
cd ts-node
npm install
npm run dev             # 或 npm run build && npm start
```

### 对比测试（所有服务启动后）

```bash
# 单核基线：concurrency=1，记录 total_time_ms
for port in 8135 8136 8137 8138 8139; do
  echo -n "port $port single: "
  curl -s -X POST http://localhost:$port/compute \
    -H 'Content-Type: application/json' \
    -d '{"task_count":8,"iterations":2000000,"concurrency":1}' | jq -r '.total_time_ms'
done

# 多核并跑：concurrency=8，与上面相除即为加速比
for port in 8135 8136 8137 8138 8139; do
  echo -n "port $port multi : "
  curl -s -X POST http://localhost:$port/compute \
    -H 'Content-Type: application/json' \
    -d '{"task_count":8,"iterations":2000000,"concurrency":8}' | jq -r '.total_time_ms'
done

# 正确性交叉校验：五门语言的 checksum 必须完全相同
for port in 8135 8136 8137 8138 8139; do
  curl -s -X POST http://localhost:$port/compute \
    -H 'Content-Type: application/json' \
    -d '{"task_count":4,"iterations":300000,"concurrency":2}' | jq -r '.checksum'
done | sort -u | wc -l    # 输出必须是 1
```

### 自动化验证

```bash
python3 .wb_verify/verify_all.py 13
```

验证器用 **Python 独立实现同一套 uint64 环绕算法作为 oracle**，逐任务比对 checksum ——
这是**契约级断言**，而非"端口能通"。位运算语义写错（Python 忘记 `& MASK`、TS 用 `number` 而非
`BigInt`、Java 用有符号输出）都能当场发现。

**预期趋势**（仅用于校验你的实测结果是否离谱，不作为结论）：

- `concurrency=1` 时，**单核性能**排序约为 Rust ≈ Go > Java > TS(BigInt) > Python；
- `concurrency=核心数` 时，四门"真并行"语言应接近线性加速（加速比 ≈ 核心数）；
  **Python 只有在用 `ProcessPoolExecutor` 时才加速**，若换成 `ThreadPoolExecutor` 会退化为 ≈1.0；
- TS 的加速比正常，但**绝对耗时被 BigInt 拖慢约一个数量级** —— 这是本场景最值得记录的"语言税"。

---

## 选型思考

### 三条结论

**1. IO 密集与 CPU 密集的结论可以完全相反。**
场景 02（IO 密集）里 Python 的 asyncio 表现良好；本场景里同样的 asyncio 完全失效。
所以"某语言并发性能如何"这个问法本身不成立 —— **必须先说清负载类型**，
这也是本仓库把两个场景分开做的原因。

**2. Python 的补救方案是"换进程"，代价不在 API 而在数据通路。**
`ProcessPoolExecutor` 只有一行，看起来很美。但真实的业务任务往往要传入大对象
（模型、数据集、连接），这些**必须 pickle 序列化**才能跨进程 ——
序列化开销可能远超计算本身。而 `ThreadPoolExecutor` 的代码一模一样却毫无加速效果，
**这是个很容易写对代码却拿不到性能的陷阱**。

**3. Node 的"语言税"集中在两处：无 64 位整数、无法共享内存。**
`BigInt` 比 `number` 慢约一个数量级；Worker 之间只能 `postMessage` 拷贝数据。
工程上的规避手段是**用 32 位双字模拟 64 位整数**（`Math.imul` 拆分高低位，可快 5~10 倍），
以及用 `SharedArrayBuffer` 传二进制大块。但两者都让代码复杂度陡增、极易写错 ——
**当业务真的需要精确 64 位整数运算时，应当重新评估是否该用 Node 做这件事。**

### 什么时候选谁

| 场景 | 推荐 | 原因 |
|------|------|------|
| 纯计算密集、延迟敏感 | **Rust** | 无 GC 暂停、无运行时抖动，编译期挡住数据竞争 |
| 计算密集但要兼顾开发效率与生态 | **Go** | goroutine + channel 原语最简洁，吞吐好，工程性好 |
| 计算密集且已在 JVM 生态内 | **Java** | 线程池模型人人会写，诊断工具（jstack/Arthas）成熟；注意线程栈内存 |
| 计算密集 + 需要 Python 生态（AI/科学计算） | **Python + C 扩展** | 别用纯 Python 硬算 —— 用 NumPy/Numba 把热点下沉到 C/Rust |
| 主要是 IO，只有少量热点计算 | **Node / Python** | 保留生态优势；热点用 worker 或原生扩展隔离出去 |

> ⚠️ **反过来说**：如果你的任务本身就是"CPU 密集 + 需要精确 64 位整数 + 高并发"，
> Node 与纯 Python 都不该是首选。这正是本场景存在的意义。
