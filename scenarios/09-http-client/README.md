# 场景 09：HTTP 客户端（超时 / 重试）

## 业务描述

统一实现 HTTP 客户端，调用外部服务，必须支持：

- **连接超时**：TCP 连接建立超时（如 3s）
- **读取超时**：服务器响应超时（如 10s）
- **自动重试**：指数退避重试（3 次）
- **熔断**：连续失败 N 次后熔断一段时间
- **请求/响应日志**：结构化记录调用链路

### 统一接口

```bash
# 调用外部 API（模拟：请求 httpbin.org）
POST /call-external
{
  "url": "https://httpbin.org/get",
  "timeout_ms": 5000,
  "retry_times": 3
}
→ {
    "status_code": 200,
    "latency_ms": 120,
    "retries": 0,
    "body": {...}
  }
```

所有语言实现**业务逻辑完全一致**。

---

## 实现清单

| 语言 | HTTP Client | 重试/熔断方案 | 连接池 |
|------|------------|-------------|--------|
| Java | Spring `WebClient` / `RestTemplate` | Resilience4j | Spring 默认连接池 |
| Go | 标准库 `http.Client` + `http.Transport` | 手动实现 / `hashicorp/go-retry` | Transport 连接池 |
| Python | `httpx`（async）+ `tenacity` | tenacity | httpx 默认连接池 |
| Rust | `reqwest` + `reqwest-middleware` | reqwest-retry | reqwest 默认连接池 |
| TS(Node) | `undici` + `@fastify/undici` | `p-retry` | undici 连接池 |

### 特别关注
- **超时粒度**：连接超时 vs 读取超时是否分开配置
- **连接池模型**：最大连接数、空闲超时、连接复用
- **原生异步支持**：Java WebClient / Go 同步 / Python async / Rust async / TS async

---

## 关键对比

| 维度 | Java | Go | Python | Rust | TS(Node) |
|------|------|----|--------|------|----------|
| **端口** | 8115 | 8116 | 8117 | 8118 | 8119 |
| **Mock 端口** | 8200 | 8201 | 8202 | 8203 | 8204 |
| **HTTP Client** | RestTemplate (Apache HttpClient 5) | http.Client + http.Transport | httpx (async) | reqwest | undici |
| **底层库** | Apache HttpClient 5 | 标准库 net/http | httpx | reqwest (tokio) | undici (原生 fetch 底层) |
| **连接池** | ✅ PoolingHttpClientConnectionManager | ✅ Transport（自动） | ✅ httpx 默认 | ✅ reqwest 默认 | ✅ undici Pool |
| **超时粒度** | ✅ connectTimeout vs readTimeout | ✅ DialContext vs ResponseHeaderTimeout | ✅ Timeout(connect/read/write) | ✅ connect_timeout + timeout() | ✅ headersTimeout + bodyTimeout + requestTimeout |
| **重试** | ✅ Resilience4j @Retry (AOP) | ✅ 手动指数退避 / go-retryablehttp | ✅ 手动（tenacity 可选） | ✅ 手动指数退避 | ✅ 手动指数退避 |
| **熔断** | ✅ Resilience4j @CircuitBreaker | ✅ 手动 / sony/gobreaker | ✅ 手动 / pybreaker | ✅ 手动 / circuits crate | ✅ 手动 / brakes |
| **异步支持** | RestTemplate 同步；WebClient 异步 | 同步 + goroutine | ✅ httpx.AsyncClient | ✅ reqwest async (tokio) | ✅ undici fetch Promise |
| **错误处理** | ResourceAccessException (超时) / HttpServerErrorException (5xx) | error + status code 检查 | httpx.TimeoutException / RequestError | reqwest::Error + 手动 match | try/catch + response.statusCode |
| **JSON 响应** | RestTemplate.getForObject | json.NewDecoder | resp.json() | resp.json::<serde_json::Value>() | resp.json() |
| **连接数上限** | maxTotal=100, maxPerRoute=20 | MaxIdleConns=100, MaxConnsPerHost=20 | 默认 + Limits(max_connections) | reqwest 默认 | connections=100 |
| **空闲连接回收** | evictIdleConnections(30s) | IdleConnTimeout=30s | httpx 默认 | reqwest 默认 | undici 默认 |
| **零依赖** | ❌ Resilience4j + HttpClient 5 | ✅ 标准库（重试/熔断手动） | ❌ httpx + fastapi | ❌ reqwest + axum | ❌ undici + fastify |
| **代码行数** | ~180 行（配置+服务+控制+Mock） | ~220 行（全手动，熔断器） | ~200 行 | ~230 行 | ~220 行 |
| **优势** | Resilience4j AOP 无侵入、Spring 无缝 | 标准库极简、goroutine 并发安全 | httpx async + tenacity 装饰器 | reqwest async-first + Rust Result 安全 | undici 是 Node fetch 底层，性能好 |
| **痛点 & 坑** | RestTemplate 同步、Resilience4j AOP 对 private 方法无效 | 手动熔断代码多、http.Client 要自己存全局实例 | httpx 不如 requests 流行、async 调试难 | reqwest 依赖 tokio 较重、Cargo 下载慢 | Node 单线程，不适合大量并发 HTTP（用 worker_threads 解）|

---

## 统一测试命令

```bash
# 每个服务启动后内置 mock server 自动启动
# 测试 /ok（立即成功）
curl -s -X POST http://localhost:8115/call-external \
  -H 'Content-Type: application/json' \
  -d '{"url":"http://localhost:8200/ok","timeout_ms":3000,"retry_times":1}'

# 测试 /slow（2s 延迟 → 5s 超时配置应该能成功，3s 会失败）
curl -s -X POST http://localhost:8115/call-external \
  -H 'Content-Type: application/json' \
  -d '{"url":"http://localhost:8200/slow","timeout_ms":1000,"retry_times":0}'
# → 应该返回 TIMEOUT

# 测试 /fail（500 → 触发重试）
curl -s -X POST http://localhost:8115/call-external \
  -H 'Content-Type: application/json' \
  -d '{"url":"http://localhost:8200/fail","timeout_ms":3000,"retry_times":2}'
# → 重试 2 次后返回 status_code: 500

# 测试外部 API（httpbin.org）
curl -s -X POST http://localhost:8115/call-external \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://httpbin.org/get","timeout_ms":5000,"retry_times":1}'

# 5 语言批量测试
echo "=== OK 测试 ==="
for port in 8115 8116 8117 8118 8119; do
  echo "--- Port $port ---"
  curl -s -X POST http://localhost:$port/call-external \
    -H 'Content-Type: application/json' \
    -d '{"timeout_ms":3000,"retry_times":1}' | jq '{status_code, latency_ms, retries, success}'
done
```

---

## 运行方式

### Java (端口 8115，Mock 8200)
```bash
cd scenarios/09-http-client/java
mise exec -- mvn spring-boot:run
```

### Go (端口 8116，Mock 8201)
```bash
cd scenarios/09-http-client/go
go mod tidy
go run main.go
```

### Python (端口 8117，Mock 8202)
```bash
cd scenarios/09-http-client/python
pip install -r requirements.txt
python main.py
```

### Rust (端口 8118，Mock 8203)
```bash
cd scenarios/09-http-client/rust
cargo run
```

### TS(Node) (端口 8119，Mock 8204)
```bash
cd scenarios/09-http-client/ts-node
npm install && npm run dev
```

---

## 选型思考

### 五种 HTTP 客户端定位

| 场景 | 推荐 | 原因 |
|------|------|------|
| **Java/Spring 项目** | ☕ RestTemplate + Resilience4j | AOP 无侵入、熔断/重试/限流一套搞定 |
| **Go 微服务** | 🐹 http.Client + Transport | 标准库极简、goroutine 天然高并发 |
| **Python async 服务** | 🐍 httpx.AsyncClient | 原生 async、比 requests 强、装饰器重试方便 |
| **Rust 高性能服务** | 🦀 reqwest | async-first、Result 安全、连接池 + 重试生态好 |
| **Node/BFF 层** | 🟦 undici | 是 Node fetch 底层、性能极佳、fastify 无缝 |

### 关键选型决策点

| 问题 | 答案 |
|------|------|
| **需要分开控制连接超时和读取超时？** | 全部都支持（各有写法） |
| **连接池调优？** | Go Transport、undici Pool、Apache HttpClient 5 都有细粒度配置 |
| **重试策略？** | 推荐**指数退避 + 抖动 + 最大超时**（不是线性重试） |
| **熔断必须要？** | 是！微服务雪崩头号杀手，必须加 |
| **同步还是异步？** | Java RestTemplate 同步够用（线程池）；Go 同步 + goroutine；Python/Rust/Node 原生 async |
| **想用 fetch 语法？** | Node 原生 fetch、Python httpx、Rust reqwest 都有类似 API |

