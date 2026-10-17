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
| Rust | `config` crate | **类型编译期**（结构体字段）+ 值启动时（手动 validate） | ✅ 支持 |
| TS(Node) | `@fastify/env` + zod / `dotenv` + zod | 启动时 | ❌ |

### 特别关注
- **校验时机分层**：Rust 的**类型安全**在编译期（字段拼错直接编译不过），**值校验**与其他语言一样在启动时；
  "Rust 编译期校验"是过度简化 —— 非法 `logging.level` 在五门语言都是启动时 fail-fast，一视同仁
- **Spring Boot 的约定优于配置** vs 其他语言显式配置
- **env 分隔符是跨语言对齐的高发坑**：见下方「契约要点」

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
| **脱敏处理** | 手动 response 排除 password | 响应专用结构体（`json:"-"` 会把脱敏值一起吞掉，见下方坑） | model.dump() 手动覆盖 | 手动 json 排除字段 | JSON.parse + 手动覆盖 |
| **优势** | Spring 无缝、注解校验自动处理 | viper 功能全、env 覆盖方便 | pydantic model 写起来简洁、类型自动 | **编译期类型安全** + config crate embed | zod 一次写两用（schema=类型=校验） |
| **痛点 & 坑** | Spring Boot 环境变量规则宽松易踩坑 | 手动校验代码啰嗦 | 动态类型运行时才发现 | config crate 的 env 分隔符默认是**空串**（须显式 `separator("__")`，且前缀分隔符要钉回 `_`）、宏复杂 | Node env 处理比编译型语言啰嗦 |

---

## 统一 env 覆盖示例

5 种语言支持相同的覆盖语义，但**分隔符不同**：

| 语言 | env key 写法 | 自动覆盖 |
|------|------------|---------|
| ☕ Java | `MYAPP_DATABASE_POOL_SIZE=30` | ✅ 自动绑定（Spring Boot 宽松规则） |
| 🐹 Go | `MYAPP_DATABASE_POOL_SIZE=30` | ✅ SetEnvKeyReplacer `.→_` |
| 🐍 Python | `MYAPP_DATABASE__POOL_SIZE=30` | ✅ `__` 分隔层级 |
| 🦀 Rust | `MYAPP_DATABASE__POOL_SIZE=30` | ⚠️ **必须显式 `separator("__")`** —— config 0.14 的默认分隔符是**空串**，不设置则 `MYAPP_DATABASE__URL` 变成单键 `database__url`，覆盖**静默失效**（且设了 `separator("__")` 后前缀分隔符会跟着变 `__`，还要 `prefix_separator("_")` 钉回来） |
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

## 契约要点（`verify_all.py` 断言什么）

本场景已从"端口监听"升级为**契约级断言**：每门语言跑**三次**，
分别钉住配置管理的三件事 —— 读得对、覆盖生效、非法配置起不来。

### 1. 基线运行：全字段 exact 契约

`GET /config` 的键集合与每个字段逐项比对（`exact=True`，多一个键少一个键都失败）：

```json
{
  "server":   {"port": 8110, "host": "0.0.0.0"},
  "database": {"url": "localhost:3306", "user": "admin",
               "password": "********", "pool_size": 10},
  "logging":  {"level": "INFO", "json": true},
  "env": "", "source": "…"
}
```

两个细节：**`server.port` 用验证器实际连接的端口** —— 把"配置里声称的端口"和
"服务真正绑定的端口"钉在一起；**`password` 必须是 `********`** —— 脱敏值本身也是契约
（Go 最初用 `json:"-"` 排除密码字段，把脱敏值一起吞了，响应里直接少 `password` 键）。

### 2. env 覆盖运行：env > 文件

`MYAPP_ENV=prod` + `url`/`level`/`pool_size` 三个 env 覆盖。关键在于
**Go 在 prod 下会改读 `config-prod.yaml`**（里面 `url=prod-db-cluster:3306`、`pool_size=20`），
env 必须赢过文件才说明优先级正确 —— 只测基线是测不出优先级问题的。

### 3. 负向运行：非法配置必须 fail-fast

`logging.level=BOGUS` 启动，**整个等待窗口内端口都不得监听**。
不判断"包装进程是否退出"（tsx watch / mvn 的包装进程会在子进程崩溃后滞留）——
端口是否释放才是可靠判据。

### 4. 本场景踩出的两个"静默失效"坑（均已修复）

1. **Go 的 `json:"-"` 把脱敏值一起吞掉**：`DatabaseConfig.Password` 带 `json:"-"` 后，
   响应结构体无论填什么都不会输出该键 —— 修复用了响应专用结构体 `DatabaseResp`。
2. **Rust config 0.14 的 env 分隔符默认是空串**：`MYAPP_DATABASE__URL` 被当成单个键
   `database__url`，永远匹配不上 `database.url`，**且不报错** —— 表现为"env 覆盖静默失效"，
   而 README 却写着"config crate 默认 `__`"。修复：`separator("__")` + `prefix_separator("_")`
   （后者也必须显式设置：设了 `separator("__")` 后前缀分隔符会跟着变成 `__`，
   导致 `MYAPP_` 开头的键全部被跳过）。这个 bug 还连带**破坏了 fail-fast** ——
   非法 level 根本传不进去，服务照常监听。

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
| **配置校验什么时候做？** | **Rust 类型编译期**（字段级）→ 五门统一**启动时 fail-fast**（值级，非法 level 端口都起不来）→ 运行时 |
| **需要热重载吗？** | viper（Go）/ config crate（Rust）内置，其他语言外接库 |
| **env 覆盖层级分隔符？** | Rust/Python/Node 统一 `__`（双下划线，Rust 须显式设置，crate 默认是空串），Spring 宽松规则，Go 自动转换 |
| **配置要 embed 进二进制（无运行时文件依赖）？** | ✅ Rust config crate + `include_str!` 其他语言做不到 |
| **配置和类型定义分离？** | Rust config crate embed 最优雅，Java/Python/TS 是两个文件 |

