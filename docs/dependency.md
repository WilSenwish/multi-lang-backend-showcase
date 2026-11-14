# 依赖管理 & 构建工具专题

> Maven / go mod / pip / Cargo / npm — 各语言依赖管理的历史包袱、设计哲学、坑。

---

## 1. 各语言依赖管理体系

### Java：Maven / Gradle

```xml
<!-- pom.xml -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
    <version>3.2.0</version>
</dependency>
```

| 维度 | Maven | Gradle |
|------|-------|--------|
| 格式 | XML POM | Groovy/Kotlin DSL |
| 仓库 | Maven Central / 私服 | 同 Maven |
| 版本锁定 | 依赖调解（最近优先） | 更强的依赖管理 |
| 构建速度 | 中 | 快（增量构建、并行） |
| 学习曲线 | 低（约定优于配置） | 中（灵活但复杂） |

- **约定优于配置**：标准目录结构，生命周期阶段
- 依赖树深时容易出现版本冲突（`mvn dependency:tree` 排查）
- Spring Boot 的 `starter` 大大简化依赖管理

### Go：go mod

```go
// go.mod
module github.com/user/myapp

go 1.22

require (
    github.com/gin-gonic/gin v1.10.0
)
```

- Go 1.11 引入 `go mod`，彻底解决 GOPATH 时代的痛点
- **语义化版本严格**：`v1.2.3`，不允许隐式升级
- 模块代理：`GOPROXY=https://proxy.golang.org,direct`
- `go.sum` 校验依赖完整性
- **没有锁文件问题**（go.mod 本身就是锁）
- 优点：简单、明确、可重现构建
- 缺点：Monorepo 支持弱，私有仓库需要额外配置

### Python：pip + pyproject.toml

```toml
# pyproject.toml
[project]
name = "myapp"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi==0.110.0",
    "uvicorn[standard]==0.29.0",
]
```

| 工具 | 特点 |
|------|------|
| pip | 最基础，单包安装 |
| pip-tools | `requirements.in` → `requirements.txt` |
| Poetry | 依赖解析 + 虚拟环境 + 打包一站式 |
| uv | 极速 pip 替代品（Rust 写的） |
| venv | 标准库虚拟环境 |

- **历史包袱最重**：pip / setuptools / requirements.txt / setup.py / setup.cfg / pyproject.toml 混战
- pyproject.toml 是 PEP 621 标准方向
- 版本冲突问题严重（pip 不做依赖解析，Poetry/uv 做）

### Rust：Cargo

```toml
# Cargo.toml
[package]
name = "myapp"
version = "0.1.0"
edition = "2021"

[dependencies]
axum = "0.7"
serde = { version = "1", features = ["derive"] }
tokio = { version = "1", features = ["full"] }
```

- **最佳实践的标杆**：一个 Cargo.toml 搞定一切
- `Cargo.lock` 锁依赖版本，保证可重现构建
- crate.io 官方仓库，生态繁荣
- `cargo build / run / test / publish` 全流程
- 支持 feature flags：按需编译，减小二进制体积
- workspace 支持：monorepo 原生支持
- 缺点：编译慢，首次下载依赖慢

### TS(Node)：npm / pnpm / yarn

```json
// package.json
{
  "name": "myapp",
  "version": "1.0.0",
  "dependencies": {
    "fastify": "^4.26.0"
  },
  "devDependencies": {
    "typescript": "^5.4.0"
  }
}
```

| 工具 | 特点 |
|------|------|
| npm | 官方，node_modules 扁平安装 |
| yarn | 快，有 lock 文件 |
| pnpm | **硬链接 + 内容寻址存储**，极省空间 |
| bun | 极快，原生 TS/JS 支持 |

- npm 生态全球最大（超过 200 万包）
- node_modules 历史悠久的问题：幽灵依赖、嵌套地狱 → pnpm 解决
- 版本语义：`^1.2.3`（兼容升级）vs `~1.2.3`（补丁升级）vs `1.2.3`（锁定）
- 安全问题：供应链攻击、typosquatting

---

## 2. 依赖管理对比表

| 维度 | Java | Go | Python | Rust | TS(Node) |
|------|------|----|--------|------|----------|
| 主工具 | Maven/Gradle | go mod | pip + pyproject | Cargo | pnpm |
| 锁文件 | ✅ (effective POM) | ✅ go.sum | ❌ (需手动) | ✅ Cargo.lock | ✅ pnpm-lock.yaml |
| 依赖解析 | 自动 | 自动 | **pip 不做** | Cargo 做 | pnpm 严格 |
| Monorepo | ✅ | ❌ (workspace 有限) | 🟡 | ✅ workspace | ✅ pnpm workspace |
| 版本锁定 | 弱 | 强 | 弱 | 强 | pnpm 强 |
| 仓库大小 | Maven Central | proxy.golang.org | PyPI | crates.io | npm（最大） |
| 编译产物 | .jar | 原生二进制 | .pyc | 原生二进制 | .js (tsc 编译) |
| 可执行分发 | java -jar | 直接二进制 | 源码 + 依赖 | 直接二进制 | node xxx.js |

---

## 3. 打包 & 部署

| 语言 | 最简部署方式 | Docker 镜像大小 |
|------|------------|----------------|
| Java | `java -jar app.jar` | ~300MB+（含 JRE） |
| Go | `./app`（静态编译） | ~10MB |
| Python | `pip install -r requirements.txt && uvicorn main:app` | ~100MB |
| Rust | `./app`（静态编译） | ~10MB |
| TS(Node) | `npm install && node dist/main.js` | ~150MB（含 Node.js） |

### 容器化最佳实践

- **Go / Rust**：多阶段构建，最终只用 `scratch` 或 `alpine` 基础镜像
- **Java**：推荐 `eclipse-temurin:jre-alpine`，或 GraalVM Native Image 编译成原生二进制
- **Python**：使用 slim 基础镜像，合并 RUN 指令减小层
- **TS(Node)**：多阶段构建，生产镜像只拷贝 dist 和 node_modules（--production）

---

## 4. 选型建议

| 场景 | 推荐 | 原因 |
|------|------|------|
| 需要原生二进制、静态部署 | Go / Rust | 单文件分发，无运行时依赖 |
| 快速原型、环境受限 | Python / TS | 不需要编译，直接运行 |
| 大型企业、依赖众多 | Java | 成熟的依赖管理和版本治理 |
| Monorepo 管理多包 | Rust / pnpm | 原生 workspace 支持 |

---

## 5. 本仓库实际使用的生产级组件

> 2026-11-14 全面升级：所有场景统一到工业级开源组件，消除手搓实现。

### Web 框架

| 语言 | 组件 | 版本 | 说明 |
|------|------|------|------|
| Java | Spring Boot | 3.2.0 | 生态最全，约定优于配置 |
| Go | **gin-gonic/gin** | v1.10.0 | Go 生态事实标准（之前用 net/http 手搓） |
| Python | FastAPI | 0.115.0 | async + Pydantic 类型安全 |
| Rust | axum | 0.7 | 零成本抽象，与 tokio 深度整合 |
| TS(Node) | Fastify | 4.x | 快，自带 pino 日志 |

### 结构化日志（最低 DEBUG 级别，JSON 输出到 stdout）

| 语言 | 组件 | 版本 | 说明 |
|------|------|------|------|
| Java | SLF4J + Logback + **logstash-logback-encoder** | 7.4 | SpringBoot 默认，LogstashEncoder 输出 JSON |
| Go | **go.uber.org/zap** | v1.27.0 | 零分配，Go 结构化日志事实标准（之前用标准库 log） |
| Python | **structlog** | 24.4.0 | 灵活链式 API，contextvars 注入链路字段（07 已有） |
| Rust | **tracing + tracing-subscriber** | 0.1 / 0.3 | tracing 是 API 层，subscriber 负责 JSON 输出（之前用 println!） |
| TS(Node) | **pino** | ^9.6.0 | Node 生态最快 JSON 日志库（07 已有） |

### 业务算法组件（替换手搓实现）

| 场景 | 语言 | 手搓实现 | → 生产级组件 | 版本 |
|------|------|---------|-------------|------|
| 09-http-client | Python | CircuitBreaker 熔断类 | **pybreaker** | 1.0.1 |
| 09-http-client | Python | 手动指数退避循环 | **tenacity** | 9.0.0 |
| 09-http-client | Python | http.server Mock Server | **httpx.MockTransport** | httpx 内置 |
| 10-rate-limit | Python | TokenBucket 类 | **slowapi** | 0.1.9 |
| 10-rate-limit | Go | 自己实现令牌桶逻辑（已用官方库） | golang.org/x/time/rate | v0.5.0 ✅ 保留 |
| 11-db-crud-pool | Go | 自己管理连接池参数 | sql.DB + SetMaxOpenConns | 标准库 ✅ 保留 |
| 12-graceful-shutdown | Go | 优雅关闭信号处理 | signal.NotifyContext + server.Shutdown | 标准库 ✅ 保留 |

### Python 根目录统一依赖（pyproject.toml）

```toml
dependencies = [
    # Web 框架
    "fastapi==0.115.0",
    "uvicorn[standard]==0.30.6",
    "pydantic==2.9.2",
    # HTTP 客户端
    "httpx==0.27.2",
    # 业务组件
    "pybreaker==1.0.1",    # 熔断（替换 09 手搓）
    "slowapi==0.1.9",      # 限流（替换 10 手搓）
    "tenacity==9.0.0",     # 重试（替换 09 手搓）
    # 日志
    "structlog==24.4.0",
    # 配置
    "pyyaml==6.0.2",
]
```

### Go 依赖（各场景 go.mod）

```
# Web 框架（16 个场景）
github.com/gin-gonic/gin v1.10.0

# 日志（16 个场景）
go.uber.org/zap v1.27.0

# 业务组件（按场景）
golang.org/x/time       v0.5.0  # 限流（场景 10）
golang.org/x/sync       v0.10.0 # errgroup（场景 15）
github.com/spf13/viper  v1.19.0 # 配置（场景 08）
```

### 环境管理

| 工具 | 用途 | 配置 |
|------|------|------|
| **uv** | Python 依赖管理 + 虚拟环境 | 根目录 `.venv`，`uv sync` 同步 pyproject.toml |
| **mise** | SDK 版本管理 | `mise.toml` 固定 `java = "zulu-17"` |
| **go mod** | Go 依赖管理 | 各场景独立 go.mod |
| **cargo** | Rust 依赖管理 | 各场景独立 Cargo.toml |
| **npm** | Node 依赖管理 | 各场景独立 package.json |
