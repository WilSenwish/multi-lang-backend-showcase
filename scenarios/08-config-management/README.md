# 场景 08：多环境配置管理

## 业务描述

统一实现多环境配置管理，支持：

- **多环境**：dev / test / prod，配置分离
- **YAML 配置**：结构化配置文件
- **环境变量覆盖**：`SPRING_DATASOURCE_URL` / `MYAPP_DB_HOST`
- **配置校验**：必填项校验、类型校验、范围校验（编译期 vs 启动时 vs 运行时）
- **热重载（可选）**：运行时修改配置生效

### 统一配置结构

```yaml
# config.yaml
server:
  port: 8080
  host: "0.0.0.0"

database:
  url: "localhost:3306"
  user: "admin"
  password: "secret"
  pool_size: 10

logging:
  level: "INFO"
  json: true
```

### 环境变量覆盖示例
```bash
# 覆盖数据库 URL
MYAPP_DATABASE_URL=prod-db:3306

# 覆盖日志级别
MYAPP_LOGGING_LEVEL=DEBUG
```

所有语言实现**业务逻辑完全一致**。

---

## 实现清单

| 语言 | 配置库 | 校验时机 | 热重载 |
|------|--------|---------|--------|
| Java | Spring Boot + `@ConfigurationProperties` | 启动时（绑定 + 校验） | Spring Cloud Config |
| Go | `viper` | 启动时 | ✅ 支持 |
| Python | `pydantic-settings` | 启动时（pydantic 校验） | ❌ |
| Rust | `figment` / `config` | **编译期**（rust config crate） | ✅ |
| TS(Node) | `@fastify/env` + zod / `dotenv` + zod | 启动时 | ❌ |

### 特别关注
- **校验时机是巨大差异点**：Rust 编译期校验 > Java/Go/Python/TS 启动时校验 > 无校验
- **Spring Boot 的约定优于配置** vs 其他语言显式配置

---

## 关键对比

| 维度 | Java | Go | Python | Rust | TS(Node) |
|------|------|----|--------|------|----------|
| **端口** | 8110 | 8111 | 8112 | 8113 | 8114 |
| **配置库** | Spring Boot @ConfigurationProperties | viper | pydantic-settings + pyyaml | config crate | zod + @fastify/env + dotenv |
| **配置来源** | application.yml + application-{profile}.yml | config.yaml + config-{env}.yaml | config.yaml + 手动 env 覆盖 | config.yaml + config-{env}.yaml | env 优先（yaml 可选） |
| **env 前缀** | 无（Spring 宽松：server.port → SERVER_PORT） | MYAPP_ + . → _ 转换 | MYAPP_ | MYAPP_ + __ 分隔层级 | MYAPP_ + __ 分隔层级 |
| **env 分隔符** | `.` 或无 | `.` 自动转 `_` | `__`（双下划线） | `__`（双下划线） | `__`（双下划线） |
| **校验时机** | 启动时（fail-fast） | 启动时（手动 Validate()） | 启动时（pydantic 自动校验） | **编译期**（类型安全）+ 启动时（值校验） | 启动时（zod 自动校验） |
| **校验能力** | @NotNull/@Min/@Pattern + @Valid 嵌套 | 手动 if + fmt.Errorf | Field(ge=, le=, min_length=) + model_validator | #[derive(Deserialize)] 编译期 + 手动 validate() | z.number().min().max() / z.enum() |
| **类型安全** | ✅ 强类型（注解绑定） | ✅ mapstructure tag 绑定 | ✅ pydantic model 类型推断 | ⭐⭐⭐⭐⭐ **编译期**（结构体字段） | ✅ zod schema = TS 类型 |
| **编译期 embed 配置** | ❌ 运行时读文件 | ❌ 运行时读文件 | ❌ 运行时读文件 | ✅ **config crate 可以 embed**（include_str!） | ❌ 运行时 |
| **热重载** | Spring Cloud Config（额外组件） | viper WatchConfig（内置） | ❌ | config crate WatchConfig | ❌ |
| **多环境** | Spring profiles + application-{profile}.yml | SetConfigName 动态切换文件名 | 手动 env 切 config file | SetConfigName 动态切换 | 手动 env |
| **依赖数量** | 2（boot-starter-web + validation） | 1（viper） | 2（pydantic + pyyaml） | 1（config crate） | 4（fastify + zod + @fastify/env + dotenv） |
| **脱敏处理** | 手动 response 排除 password | 手动 struct 排除 json tag | model.dump() 手动覆盖 | 手动 json 排除字段 | JSON.parse + 手动覆盖 |
| **优势** | Spring 无缝、注解校验自动处理 | viper 功能全、env 覆盖方便 | pydantic model 写起来简洁、类型自动 | **编译期类型安全** + config crate embed | zod 一次写两用（schema=类型=校验） |
| **痛点 & 坑** | Spring Boot 环境变量规则宽松易踩坑 | 手动校验代码啰嗦 | 动态类型运行时才发现 | config crate __ 分隔和其他语言不一致、宏复杂 | Node env 处理比编译型语言啰嗦 |

---

## 统一 env 覆盖示例

5 种语言支持相同的覆盖语义，但**分隔符不同**：

| 语言 | env key 写法 | 自动覆盖 |
|------|------------|---------|
| ☕ Java | `MYAPP_DATABASE_POOL_SIZE=30` | ✅ 自动绑定（Spring Boot 宽松规则） |
| 🐹 Go | `MYAPP_DATABASE_POOL_SIZE=30` | ✅ SetEnvKeyReplacer `.→_` |
| 🐍 Python | `MYAPP_DATABASE__POOL_SIZE=30` | ✅ `__` 分隔层级 |
| 🦀 Rust | `MYAPP_DATABASE__POOL_SIZE=30` | ✅ config crate 默认 `__` |
| 🟦 TS | `MYAPP_DATABASE__POOL_SIZE=30` | ✅ `__` 分隔层级 |

### 统一测试命令
```bash
# 覆盖端口为 9999 + 数据库地址
MYAPP_SERVER_PORT=9999 MYAPP_DATABASE_URL=prod-db:3306

# 各语言分别启动（端口仍按各自默认）
# Java:    MYAPP_DATABASE_URL=prod-db:3306 MYAPP_LOGGING_LEVEL=DEBUG mvn spring-boot:run
# Go:      MYAPP_DATABASE_URL=prod-db:3306 MYAPP_LOGGING_LEVEL=DEBUG go run main.go
# Python:  MYAPP_DATABASE__URL=prod-db:3306 MYAPP_LOGGING__LEVEL=DEBUG python main.py
# Rust:    MYAPP_DATABASE__URL=prod-db:3306 MYAPP_LOGGING__LEVEL=DEBUG cargo run
# TS:      MYAPP_DATABASE__URL=prod-db:3306 MYAPP_LOGGING__LEVEL=DEBUG npm run dev
```

---

## 运行方式

### Java (端口 8110)
```bash
cd scenarios/08-config-management/java
mise exec -- mvn spring-boot:run
# dev 环境
SPRING_PROFILES_ACTIVE=dev mise exec -- mvn spring-boot:run
```

### Go (端口 8111)
```bash
cd scenarios/08-config-management/go
go mod tidy   # 首次下载 viper
go run main.go
# prod 环境
MYAPP_ENV=prod MYAPP_DATABASE_URL=prod-db:3306 go run main.go
```

### Python (端口 8112)
```bash
cd scenarios/08-config-management/python
pip install -r requirements.txt
python main.py
# 环境变量覆盖
MYAPP_DATABASE__URL=prod-db:3306 MYAPP_LOGGING__LEVEL=DEBUG python main.py
```

### Rust (端口 8113)
```bash
cd scenarios/08-config-management/rust
cargo run
# prod 环境 + env 覆盖
MYAPP_ENV=prod MYAPP_DATABASE__URL=prod-db:3306 cargo run
```

### TS(Node) (端口 8114)
```bash
cd scenarios/08-config-management/ts-node
npm install && npm run dev
# 环境变量覆盖
MYAPP_DATABASE__URL=prod-db:3306 MYAPP_LOGGING__LEVEL=DEBUG npm run dev
```

### 批量测试
```bash
echo "=== 读取 config ==="
for port in 8110 8111 8112 8113 8114; do
  echo "--- Port $port ---"
  curl -s http://localhost:$port/config | jq -c .
done
```

---

## 选型思考

### 五种配置管理定位

| 场景 | 推荐 | 原因 |
|------|------|------|
| **Java/Spring Boot 项目** | ☕ @ConfigurationProperties | Spring Boot 自动绑定 + 注解校验，最省心 |
| **Go 微服务 / CLI 工具** | 🐹 viper | 支持多格式（yaml/json/toml/env）+ 热重载 |
| **Python 项目** | 🐍 pydantic-settings | pydantic 自动校验 + env + yaml，写起来短 |
| **Rust 高性能服务** | 🦀 config crate | **编译期类型安全** + embed 默认配置进二进制 |
| **Node/BFF 层** | 🟦 zod + @fastify/env | zod schema 即类型即校验，一次写两用 |

### 关键选型决策点

| 问题 | 答案 |
|------|------|
| **配置校验什么时候做？** | **Rust 编译期**（最安全）→ 其他语言启动时（fail-fast）→ 运行时 |
| **需要热重载吗？** | viper（Go）/ config crate（Rust）内置，其他语言外接库 |
| **env 覆盖层级分隔符？** | Rust/Python/Node 统一 `__`（双下划线），Spring 宽松规则，Go 自动转换 |
| **配置要 embed 进二进制（无运行时文件依赖）？** | ✅ Rust config crate + `include_str!` 其他语言做不到 |
| **配置和类型定义分离？** | Rust config crate embed 最优雅，Java/Python/TS 是两个文件 |

