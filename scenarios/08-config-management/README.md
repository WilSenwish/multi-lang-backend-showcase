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
| **配置格式** | | | | | |
| **环境变量覆盖** | | | | | |
| **校验时机** | | | | | |
| **类型校验** | | | | | |
| **热重载** | | | | | |
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

