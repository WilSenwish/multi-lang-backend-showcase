# 场景 10：单机内存限流

## 业务描述

统一实现**单机内存级**限流中间件，使用**令牌桶算法**：

- **限流规则**：每分钟允许 60 个请求（QPS=1）
- **令牌桶**：桶容量 10，以 QPS 速率填充
- **HTTP 中间件**：接入 `/api/heavy` 端点
- **拒绝响应**：限流时返回 429 + Retry-After header

### 统一接口

```bash
# 正常请求（未限流）
GET /api/heavy
→ 200 OK

# 被限流时
GET /api/heavy
→ 429 Too Many Requests
→ Retry-After: 1
→ {"error": "rate limit exceeded", "retry_after_ms": 1000}
```

> **不引入 Redis**，只做单机内存限流，降低 Demo 复杂度。

所有语言实现**业务逻辑完全一致**。

---

## 实现清单

| 语言 | 限流库/实现 | 并发安全 | 备注 |
|------|-----------|---------|------|
| Java | Guava RateLimiter / 手写令牌桶 | AtomicLong + ReentrantLock | Guava 成熟稳定 |
| Go | `golang.org/x/time/rate`（令牌桶） | 原子操作 / 锁 | Go 社区标准 |
| Python | `aiometer` / 手写 asyncio.Lock | asyncio.Lock / threading.Lock | Python 多线程注意 GIL |
| Rust | `tokio` + `governor` | 编译期保证 + 无锁 | governor 支持多种算法 |
| TS(Node) | `rate-limiter-flexible` | 单线程天然避免竞争 | Redis 或内存实现 |

### 特别关注
- **并发安全实现差异**：原子操作 vs 锁 vs 无锁 vs 单线程天然避免
- **Go 官方 `x/time/rate` 是经典实现**
- **Rust governor 支持 TokenBucket / FixedWindow / SlidingWindow**

---

## 关键对比

| 维度 | Java | Go | Python | Rust | TS(Node) |
|------|------|----|--------|------|----------|
| **端口** | 8120 | 8121 | 8122 | 8123 | 8124 |
| **限流实现** | 手写 TokenBucket（ReentrantLock） | golang.org/x/time/rate（Go 官方） | 手写 TokenBucket | 手写 TokenBucket（Mutex） | 手写 TokenBucket |
| **并发安全方式** | ReentrantLock + synchronized | atomic + channel（Ken Thompson 徒弟写的） | **单线程 asyncio → 无锁** | Mutex<State>（编译器强制检查） | **单线程事件循环 → 无锁** |
| **算法** | 令牌桶 | 令牌桶 | 令牌桶 | 令牌桶 | 令牌桶 |
| **配置** | qps=1, burst=10 | qps=1, burst=10 | qps=1, burst=10 | qps=1, burst=10 | qps=1, burst=10 |
| **TryAcquire** | limiter.tryAcquire() | limiter.Allow() | try_acquire() | try_acquire() | tryAcquire() |
| **Retry-After 计算** | 手动计算 reserve 时间 | limiter.Reserve().Delay() | 手动计算 deficit | 手动计算 deficit | 手动计算 deficit |
| **429 + Retry-After** | ✅ Response + header | ✅ w.Header().Set | ✅ JSONResponse + headers | ✅ AppendHeaders | ✅ reply.code().header() |
| **代码行数** | ~100 行（含 Guava + 手写两个版本） | ~90 行 | ~80 行 | ~100 行 | ~90 行 |
| **性能排序** | 3️⃣ ReentrantLock 有开销 | 1️⃣ x/time/rate 零分配 | 4️⃣ Python 循环慢 | 1️⃣ Mutex + Rust 无 GC | 2️⃣ Node 单线程快 |
| **优势** | Guava 成熟稳定 | Go 官方库、零分配、极简 | 单线程无锁、代码短 | 编译器强制安全 + governor 生态 | 单线程无锁 + 快 |
| **痛点 & 坑** | Guava 3MB + 手写代码多 | 要下载 golang.org/x/time | Python 单线程 = 单 worker 才安全 | governor crate 额外依赖 | Node 单线程 CPU 密集会阻塞 |

---

## 契约要点（验证强度加强计划批次 5）

场景 10 已在批次 5（2026-10-17）从「端口监听级」升级为**契约级断言**（`verify_10`），
`python3 .wb_verify/verify_all.py 10` → **5/5 全绿**。契约覆盖四道关：

- **health 真实暴露限流参数**：`/health` 必须返回 `qps`（=1）与 `burst`（=10），把「配置声称的限流速率」
  和「真实生效的速率」钉在一起（专门抓 Java 令牌桶不暴露 getter 的缺陷）。
- **突发限流生效**：连打 24 个 `/api/heavy`，前 9~11 个 200、其余 429（令牌桶容量 10 耗尽）。
- **429 退避秒数合理**：每个 429 必须带 `Retry-After` 头且落在 **1~2 秒**；body 的 `retry_after_ms`
  若出场须落在 [300, 2000]ms。两道关分别抓 Go 的退避膨胀（不 Cancel 会涨到 15s+）与 Java 的令牌桶换算错误。
- **冷却可恢复**：429 后冷却 1.5s 再请求必须回到 200（令牌已补充）—— 抓「令牌永不补充」类缺陷。

> ⚠️ **实现坑（已在批次 5 修复）**：
> - **Go**：`rate.Reserve()` 拿到 reservation 后若不使用必须 `Cancel()`，否则白占未来令牌，`Retry-After` 持续膨胀。
> - **TS(Node)**：429 响应必须用处理器形参 `reply`，写 `fastify.code(429)` 会因 `fastify.code` 不是函数
>   而让每个限流请求直接 500（端口监听级完全看不见）。
> - **Java**：手写令牌桶的微令牌单位（×1e6）与纳秒换算极易写反，导致 `retry_after_ms` 放大、令牌几乎不补充；
>   务必单独补 `getQps()`/`getBurst()` 让 health 能暴露速率。

---

## 统一测试命令

```bash
# 快速测试（连打 15 次，前 10 通过，后 5 被限流）
echo "=== 限流测试（15 次快速请求）==="
for port in 8120 8121 8122 8123 8124; do
  echo "--- Port $port ---"
  ok=0; limit=0
  for i in $(seq 1 15); do
    code=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:$port/api/heavy)
    [ "$code" = "200" ] && ok=$((ok+1)) || limit=$((limit+1))
  done
  echo "200=$ok, 429=$limit"
done

# 验证 Retry-After header
curl -s -i http://localhost:8121/api/heavy | grep -E 'HTTP|Retry-After'
```

---

## 运行方式

### Java (端口 8120)
```bash
cd scenarios/10-rate-limit/java
mise exec -- mvn spring-boot:run
```

### Go (端口 8121)
```bash
cd scenarios/10-rate-limit/go
go mod tidy
go run main.go
```

### Python (端口 8122)
```bash
cd scenarios/10-rate-limit/python
pip install -r requirements.txt
python main.py
```

### Rust (端口 8123)
```bash
cd scenarios/10-rate-limit/rust
cargo run
```

### TS(Node) (端口 8124)
```bash
cd scenarios/10-rate-limit/ts-node
npm install && npm run dev
```

---

## 选型思考

### 五种限流实现定位

| 场景 | 推荐 | 原因 |
|------|------|------|
| **Java/Spring Boot** | ★ Guava RateLimiter + 手写令牌桶 | Guava 成熟稳定，手写版更精确 |
| **Go 微服务** | 🐹 golang.org/x/time/rate | Go 官方、零分配、极简、社区标准 |
| **Python async 服务** | 🐍 手写（asyncio 单线程无需锁） | 单线程事件循环天然安全 |
| **Rust 高性能** | 🦀 governor crate | Rust 生态最成熟 + 编译期安全 |
| **Node/BFF** | 🟦 rate-limiter-flexible / 手写 | Node 单线程天然安全 |

### 关键选型决策点

| 问题 | 答案 |
|------|------|
| **并发安全靠什么？** | Go/Python/Node 单线程 → 天然安全；Java/Rust 多线程 → 必须加锁/原子 |
| **单机还是分布式？** | 本文只做单机内存。分布式用 Redis + Lua 脚本 |
| **令牌桶 vs 漏桶？** | 令牌桶允许突发流量（适合 API）；漏桶匀速（适合流量整形） |
| **固定窗口 vs 滑动窗口？** | 令牌桶最经典；固定窗口边界有突刺；滑动窗口平滑 |
| **限流要在哪一层做？** | **网关层最有效**（API Gateway / Nginx limit_req_zone）→ 服务本身也要加防雪崩 |
| **被限流返回什么？** | 429 Too Many Requests + Retry-After header（HTTP 标准） |

