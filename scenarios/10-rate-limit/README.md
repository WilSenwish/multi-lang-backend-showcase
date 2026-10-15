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
| **限流算法** | | | | | |
| **并发安全** | | | | | |
| **实现复杂度** | | | | | |
| **性能** | | | | | |
| **中间件接入** | | | | | |
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

