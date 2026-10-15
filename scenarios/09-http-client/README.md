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
| **HTTP Client** | | | | | |
| **超时粒度** | | | | | |
| **连接池** | | | | | |
| **重试/熔断** | | | | | |
| **原生异步** | | | | | |
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

