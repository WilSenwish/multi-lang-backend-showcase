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
# 调用外部 API（缺省 url 时打内置 mock /ok）
POST /call-external
{
  "url": "http://localhost:8200/ok",
  "timeout_ms": 5000,
  "retry_times": 3
}
→ {
    "status_code": 200,
    "latency_ms": 120,
    "retries": 0,
    "success": true,
    "body_preview": {"ok": true, "service": "java-mock"},
    "url": "http://localhost:8200/ok",
    "timestamp": "2026-10-17T12:00:00Z"
  }
```

> 字段名是 `body_preview`（截断预览，不是完整 body）；三个入参全部可缺省
> （缺省 url=内置 mock /ok、timeout_ms=5000、retry_times=2），**显式传 0 是合法值**
> （`retry_times=0` = 不重试）—— 五门语言都必须用"缺省 vs 显式 0"可区分的写法
> （Go 指针字段、TS `??`、Rust/Java `#[serde(default)]`/包装类型）。
> 失败与熔断响应的键集合见下方「契约要点」。

所有语言实现**业务逻辑完全一致**。

---

## 实现清单

| 语言 | HTTP Client | 重试方案 | 熔断方案 | 连接池 |
|------|------------|---------|---------|--------|
| Java | Apache HttpClient 5（`PoolingHttpClientConnectionManager`，逐请求 `RequestConfig` 超时） | 手动指数退避（次数取请求体 `retry_times`） | Resilience4j 2.2.0（`spring-boot3` starter + 编程式 `executeSupplier()`） | HC5 池（`setConnectionManagerShared(true)`） |
| Go | 标准库 `http.Client` + `http.Transport` | 手动指数退避 | 手动实现（阈值 3 次连续失败） | Transport 连接池 |
| Python | `httpx`（async） | 手动指数退避（tenacity 仅备选，见 requirements） | 手动实现（阈值 3 次连续失败） | httpx 默认连接池 |
| Rust | `reqwest` | 手动指数退避 | 手动实现（阈值 3 次连续失败） | reqwest 默认连接池 |
| TS(Node) | `undici` | 手动指数退避 | 手动实现（阈值 3 次连续失败） | undici Pool |

### 特别关注
- **超时粒度**：连接超时 vs 读取超时是否分开配置；TS 的 undici 自带定时器有 1s 地板（见下方坑）
- **连接池模型**：最大连接数、空闲超时、连接复用
- **原生异步支持**：Java 同步（HC5） / Go 同步 / Python async / Rust async / TS async
- **入参"缺省 vs 显式 0"**：`retry_times=0` 必须是不重试，不能被吞成默认值

---

## 关键对比

| 维度 | Java | Go | Python | Rust | TS(Node) |
|------|------|----|--------|------|----------|
| **端口** | 8115 | 8116 | 8117 | 8118 | 8119 |
| **Mock 端口** | 8200 | 8201 | 8202 | 8203 | 8204 |
| **HTTP Client** | Apache HttpClient 5（逐请求 RequestConfig） | http.Client + http.Transport | httpx (async) | reqwest | undici |
| **底层库** | Apache HttpClient 5 | 标准库 net/http | httpx | reqwest (tokio) | undici (原生 fetch 底层) |
| **连接池** | ✅ PoolingHttpClientConnectionManager | ✅ Transport（自动） | ✅ httpx 默认 | ✅ reqwest 默认 | ✅ undici Pool |
| **超时粒度** | ✅ connectTimeout vs responseTimeout（逐请求） | ✅ DialContext vs ResponseHeaderTimeout | ✅ Timeout(connect/read/write) | ✅ connect_timeout + timeout() | ⚠️ 必须用 AbortSignal deadline（自带定时器有 1s 地板，见下） |
| **重试** | ✅ 手动指数退避（次数取请求体 retry_times） | ✅ 手动指数退避 | ✅ 手动指数退避（tenacity 可选） | ✅ 手动指数退避 | ✅ 手动指数退避 |
| **熔断** | ✅ Resilience4j 2.2.0 编程式 executeSupplier() | ✅ 手动（阈值 3 次连续失败） | ✅ 手动（阈值 3 次连续失败） | ✅ 手动（阈值 3 次连续失败） | ✅ 手动（阈值 3 次连续失败） |
| **异步支持** | HC5 同步（线程池） | 同步 + goroutine | ✅ httpx.AsyncClient | ✅ reqwest async (tokio) | ✅ undici fetch Promise |
| **错误处理** | ExternalCallException（携带响应 map 上抛，让熔断器记失败） | error + status code 检查 | httpx.TimeoutException / RequestError | reqwest::Error + 手动 match | try/catch + response.statusCode（AggregateError 要展平） |
| **JSON 响应** | parseBody：body 解析成 JSON 对象 | json.NewDecoder | resp.json() | resp.json::<serde_json::Value>() | await body.text() + JSON.parse |
| **连接数上限** | maxTotal=100, maxPerRoute=20 | MaxIdleConns=100, MaxConnsPerHost=20 | 默认 + Limits(max_connections) | reqwest 默认 | connections=100 |
| **空闲连接回收** | evictIdleConnections(30s) | IdleConnTimeout=30s | httpx 默认 | reqwest 默认 | undici 默认 |
| **零依赖** | ❌ Resilience4j + HttpClient 5 | ✅ 标准库（重试/熔断手动） | ❌ httpx + fastapi | ❌ reqwest + axum | ❌ undici + fastify |
| **代码行数** | ~260 行（配置+服务+控制+Mock） | ~220 行（全手动，熔断器） | ~200 行 | ~230 行 | ~220 行 |
| **优势** | Resilience4j 生态全（限流/隔离开箱即用）、HC5 连接池成熟 | 标准库极简、goroutine 并发安全 | httpx async、FastAPI 声明式 | reqwest async-first + Rust Result 安全 | undici 是 Node fetch 底层，性能好 |
| **痛点 & 坑** | Resilience4j starter **版本必须对齐 Boot 主版本**（boot2 starter 在 Boot 3 下注解静默失效）；HC5 的 manager 与 client 生命周期要手动解耦 | 手动熔断代码多、http.Client 要自己存全局实例 | httpx 不如 requests 流行、async 调试难 | reqwest 依赖 tokio 较重、Cargo 下载慢 | undici 自带定时器 1s 地板；`import { request }` 会被处理器形参遮蔽 |

---

## 统一测试命令

```bash
# 每个服务启动后内置 mock server 自动启动
# 测试 /ok（立即成功）
curl -s -X POST http://localhost:8115/call-external \
  -H 'Content-Type: application/json' \
  -d '{"url":"http://localhost:8200/ok","timeout_ms":3000,"retry_times":1}'

# 测试 /slow（2s 延迟 → timeout_ms=1000 应该超时失败）
curl -s -X POST http://localhost:8115/call-external \
  -H 'Content-Type: application/json' \
  -d '{"url":"http://localhost:8200/slow","timeout_ms":1000,"retry_times":0}'
# → success=false, status_code=0, error 以 TIMEOUT 开头（各语言异常类型名不同，
#   契约只要求非空；Python 形如 "TIMEOUT: ReadTimeout"）
# → 且 latency_ms 在 400~1500 之间（等到了超时点，但没等满 mock 的 2s）

# 测试 /fail（500 → 触发重试）
curl -s -X POST http://localhost:8115/call-external \
  -H 'Content-Type: application/json' \
  -d '{"url":"http://localhost:8200/fail","timeout_ms":3000,"retry_times":2}'
# → 重试 2 次后返回 status_code: 500（重试耗尽返回真实状态码，不是 0）
# → latency_ms ≥ 250（100+200ms 退避和的下界）

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

## 契约要点（`verify_all.py` 断言什么）

本场景已从"端口监听"升级为**契约级断言**（11 个用例 × 5 语言，逐字段比对）。
契约分三层，全部有对应的反向对照实验证明"有牙齿"（见 VERIFICATION.md §12 批次 4）。

### 1. 响应键集合：三种形态跨语言逐字段一致

| 形态 | 键集合 |
|------|--------|
| 成功 | `status_code, latency_ms, retries, success, body_preview, url, timestamp` |
| 失败 | `status_code, latency_ms, retries, success, error, url, timestamp` |
| 熔断中 | 失败形态（`status_code=0` / `latency_ms=0` / `retries=0` / `error="CIRCUIT_OPEN: 熔断中"`） |

### 2. 熔断状态机：用例顺序即时间线

```
2 次成功 → 超时 / 连接拒绝 / 5xx 三连失败（第 3 次失败照常执行并记账）
→ 第 4 次调用被拒（latency_ms==0 证明连 HTTP 尝试都没发生）
→ /health 报 cb_state=open → 再打 /ok 仍被熔断
```

`/health` 响应含 `service` / `mock_port` / `cb_state` 三字段（`mock_port` 的类型逐语言声明：
Go 是字符串，其余为数字 —— 库的返回值类型差异，不强行抹平）。

### 3. 耗时上下界：证明"等待真的发生了"

| 用例 | 下界 | 上界 | 证明什么 |
|------|------|------|---------|
| 超时（timeout=500, r=0） | 400ms | 1500ms | 下界：等到了 500ms 超时点；上界：没等满 mock 的 2s、也没重试风暴 |
| 连接拒绝（r=1） | 50ms | 3000ms | 100ms 退避真的发生了 |
| 5xx 重试耗尽（r=2） | 250ms | 6000ms | 100+200ms 退避和的下界 |

只断言 `retries` 计数是抓不到"退避被清零"的 —— 把退避改成 0，计数/状态码/熔断全部正确，
**只有耗时下界能击穿它**。

### 4. 本场景踩出的五个坑（均已修复，写在这里防止复发）

1. **undici 自带定时器有 1s 地板**：`headersTimeout`/`bodyTimeout` 走的是 ~499ms tick 一次的
   快定时器（`RESOLUTION_MS=1000`），传 500ms 实测 ~1000ms 才触发，**比请求级 deadline 还慢**。
   亚秒超时必须用 `AbortController` + `setTimeout(deadline)`。
2. **`import { request } from 'undici'` 会被 fastify 处理器形参遮蔽**：处理器签名
   `async (request) => {...}` 里的 `request` 是 fastify 的请求对象，同名 import 被完全遮住，
   每个 `/call-external` 都抛 "request is not a function" —— **端口监听级验证完全瞎**。
   必须 `import { request as undiciRequest }`。
3. **`||` 会吞掉显式 0**：`reqBody.timeout_ms ?? 5000` 不能写成 `||`，否则 `timeout_ms=0`/
   `retry_times=0` 被吞成默认值（Go 侧同理：非指针 int 分不清"缺省"与"显式 0"）。
4. **Resilience4j 的 starter 必须对齐 Spring Boot 主版本**：`resilience4j-spring-boot2:1.7.1`
   的自动配置注册是 Boot 2 的 `spring.factories` 格式，Boot 3 根本不读 —— 注解全部静默失效。
   正确组合是 `resilience4j-spring-boot3:2.2.0`；本实现最终走编程式 `cb.executeSupplier()`。
   另：`application.properties` 里不能抄 YAML 语法（`resilience4j:` 缩进键谁也匹配不上，
   表现为"配置写了但全程用默认值"）。
5. **HC5 的连接池与 client 生命周期要解耦**：`HttpClientBuilder` 默认把外部传入的 manager
   视为 owned，`client.close()` 会 shutdown 整个池（后续请求全部 "Connection pool shut down"）——
   必须 `setConnectionManagerShared(true)`。

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
| **Java/Spring 项目** | ☕ Apache HC5 + Resilience4j（版本对齐 Boot） | 连接池成熟、熔断/重试/限流生态全；starter 选错主版本会静默失效 |
| **Go 微服务** | 🐹 http.Client + Transport | 标准库极简、goroutine 天然高并发 |
| **Python async 服务** | 🐍 httpx.AsyncClient | 原生 async、比 requests 强 |
| **Rust 高性能服务** | 🦀 reqwest | async-first、Result 安全、连接池 + 重试生态好 |
| **Node/BFF 层** | 🟦 undici | 是 Node fetch 底层、性能极佳、fastify 无缝 |

### 关键选型决策点

| 问题 | 答案 |
|------|------|
| **需要分开控制连接超时和读取超时？** | 全部都支持（各有写法）；Node 侧注意 undici 自带定时器的 1s 地板，亚秒超时用 AbortSignal |
| **连接池调优？** | Go Transport、undici Pool、Apache HttpClient 5 都有细粒度配置 |
| **重试策略？** | 推荐**指数退避 + 抖动 + 最大超时**（不是线性重试）；本场景统一 100→200→400ms |
| **熔断必须要？** | 是！微服务雪崩头号杀手，必须加；且要区分"5xx 也是失败"—— 把 500 记成成功会让熔断器永远打不开 |
| **同步还是异步？** | Java HC5 同步够用（线程池）；Go 同步 + goroutine；Python/Rust/Node 原生 async |
| **想用 fetch 语法？** | Node 原生 fetch、Python httpx、Rust reqwest 都有类似 API |
| **重试次数来自请求体怎么办？** | 手动退避循环比装饰器直接 —— tenacity/p-retry 的固定 stop 条件要动态化，且"读完 body 再决定是否重试"（5xx 也要消费响应体）时裸循环更直观 |

