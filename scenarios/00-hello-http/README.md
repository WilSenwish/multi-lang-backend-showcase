# 场景 00：最小 HTTP 服务

## 业务描述

实现一个最简 HTTP 服务，统一 API 契约：

```
GET /hello?name={xxx}
→ 200 OK
→ Content-Type: application/json
→ {"msg": "hello {xxx}"}

# name 参数缺省时
GET /hello
→ {"msg": "hello world"}
```

所有语言实现**业务逻辑完全一致**，仅技术栈和风格不同。

### 统一 API 契约（验证器逐字段断言）

除 README 记载的主路径外，边界行为也纳入契约，五门语言必须一致：

| 用例 | 请求 | 期望响应 |
|------|------|---------|
| 缺省 name | `GET /hello` | 200 `{"msg":"hello world"}`，`Content-Type: application/json` |
| 显式 name | `GET /hello?name=Trae` | 200 `{"msg":"hello Trae"}` |
| 空 name | `GET /hello?name=` | 200 `{"msg":"hello world"}`（空串按缺省处理） |
| unicode name | `GET /hello?name=世界` | 200 `{"msg":"hello 世界"}`（原样拼接，不转义） |
| 未匹配路径 | `GET /nope` | 404（响应体因框架而异，只断言状态码） |
| 方法不允许 | `POST /hello` | 405（响应体因框架而异，只断言状态码） |

> **加强验证时发现的差异**：fastify 对"路径匹配但方法不匹配"默认返回 **404**，
> 而 Spring / net-http / FastAPI / axum 都返回 **405**。TS 实现已改用 `fastify.all`
> 显式抹平（见 `ts-node/src/main.ts` 注释）。这类差异在"端口通不通"的判定下永远看不见。

---

## 实现清单

| 语言 | 框架 / 运行时 | 端口 | 启动命令 |
|------|-------------|------|---------|
| Java | SpringBoot 2.1.3 + Jackson + logback-spring.xml | 8080 | `mvn spring-boot:run` |
| Go | **gin-gonic/gin** + zap 结构化日志 | 8081 | `go run main.go` |
| Python | FastAPI + Uvicorn + structlog | 8082 | `../../../.venv/bin/python main.py` |
| Rust | axum + tokio + serde + tracing | 8083 | `cargo run` |
| TS(Node) | fastify + zod + pino | 8084 | `npm run dev` |

---

## 关键对比

| 维度 | Java | Go | Python | Rust | TS(Node) |
|------|------|----|--------|------|----------|
| **类型系统** | 强静态，Spring 启动时校验 | 强静态，编译期 | 动态类型（Pydantic 运行时校验） | 强静态，编译期 | 渐进式类型（zod 运行时校验） |
| **依赖 & 构建** | Maven，pom.xml | go mod，go.mod | pip + requirements.txt | Cargo，Cargo.toml | npm/pnpm，package.json |
| **并发模型** | JVM 线程池（Tomcat 默认 10-200） | Goroutine 无限扩缩 | asyncio 单线程协程 | tokio 多线程工作窃取 | 单线程事件循环 + libuv |
| **错误处理** | 未捕获异常 → 500 | `if err != nil` 显式处理 | FastAPI 自动捕获 → 500 | 编译期必须处理 | fastify 自动捕获 → 500 |
| **内存 / 启动** | JVM 预热慢（~3-10s），内存 ~200MB+ | 瞬间启动（<10ms），内存 ~5MB | 启动快（<500ms），内存 ~30MB | 瞬间启动（<10ms），内存 ~8MB | 启动中（~500ms），内存 ~60MB |
| **优势** | 生态最全，企业级稳定 | 极简快速，静态编译单文件 | 开发最快，Pydantic 校验强 | 编译期安全，零 GC，极致性能 | 异步高效，TS 类型安全 |
| **痛点 & 坑** | 启动慢，内存大，依赖重 | 错误处理样板多，没有泛型（1.18 之前） | GIL 限制 CPU 密集，依赖地狱 | 学习曲线陡峭，编译慢 | 单线程 CPU 密集弱，Node 运行时大 |

---

## 运行方式

### Java
```bash
cd scenarios/00-hello-http/java
mvn spring-boot:run
curl http://localhost:8080/hello?name=Trae
```

### Go
```bash
cd scenarios/00-hello-http/go
go mod tidy && go run main.go
curl http://localhost:8081/hello?name=Trae
```

### Python
```bash
cd scenarios/00-hello-http/python
pip install -r requirements.txt
uvicorn main:app --port 8082
curl http://localhost:8082/hello?name=Trae
```

### Rust
```bash
cd scenarios/00-hello-http/rust
cargo run
curl http://localhost:8083/hello?name=Trae
```

### TS-Node
```bash
cd scenarios/00-hello-http/ts-node
npm install && npm run dev
curl http://localhost:8084/hello?name=Trae
```

---

## 选型思考

| 场景 | 推荐语言 | 原因 |
|------|---------|------|
| **需要静态单文件部署**（K8s sidecar、CLI 工具） | **Go / Rust** | 无运行时依赖，直接二进制分发 |
| **企业业务系统、已有 JVM 生态** | **Java** | 和现有系统无缝集成，成熟稳定 |
| **快速原型、AI 应用** | **Python** | Pydantic + FastAPI 开发效率最高 |
| **高性能中间件、安全敏感** | **Rust** | 编译期内存安全 + 极致性能 |
| **BFF 层、前端后端一体化** | **TS(Node)** | TypeScript + fastify 异步高效 |

### 冷启动对比（参考数据）

| 语言 | 冷启动耗时 | 内存占用 |
|------|-----------|---------|
| Java | 3-10s | 200-500MB |
| Go | <10ms | 5-10MB |
| Python | <500ms | 20-40MB |
| Rust | <10ms | 5-10MB |
| TS-Node | <500ms | 50-80MB |

> 数据为 Docker 容器内测量的典型值，具体因配置而异。

### QPS 压测对比（wrk）

> 本仓库**不提供预置的压测数值**：QPS 与尾延迟高度依赖机器配置、SDK 版本、JVM/GC 参数与压测并发数，
> 照抄他人数字没有意义。请按下面命令在本机跑一次，把结果填进下表自用。

```bash
brew install wrk                    # macOS；Linux 用发行版包管理器

# 先按上文启动 5 个服务，再一键压测（脚本会依次打 8080-8084）
bash ../../../bench/http-bench.sh

# 或单独压某一个
wrk -t4 -c100 -d30s 'http://localhost:8081/hello?name=world'
```

| 语言 | 端口 | QPS | p99 延迟 |
|------|------|-----|---------|
| Java (SpringBoot) | 8080 | 自测填写 | 自测填写 |
| Go | 8081 | 自测填写 | 自测填写 |
| Python (FastAPI) | 8082 | 自测填写 | 自测填写 |
| Rust (axum) | 8083 | 自测填写 | 自测填写 |
| TS-Node (fastify) | 8084 | 自测填写 | 自测填写 |

**预期趋势**（不作为结论，仅用于校验你的实测结果是否离谱）：Rust / Go 通常显著领先；
Java（SpringBoot）在预热完成后吞吐接近 Rust/Go，但冷启动与内存占用明显更高；
Python(FastAPI) 与 TS-Node(fastify) 同处第二梯队，前者受 GIL 与 ASGI 框架开销影响，后者受单线程事件循环影响。

---

## 延伸阅读

- [Go 官方 HTTP 文档](https://pkg.go.dev/net/http)
- [FastAPI 官方文档](https://fastapi.tiangolo.com/)
- [axum 官方文档](https://docs.rs/axum/latest/axum/)
- [fastify 官方文档](https://www.fastify.io/)
- [SpringBoot Web 官方文档](https://docs.spring.io/spring-boot/docs/current/reference/htmlsingle/#web)
