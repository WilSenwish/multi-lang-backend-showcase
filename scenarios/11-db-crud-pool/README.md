# 场景 11：MySQL CRUD + 连接池

## 业务描述

统一实现简单的 **User 表 CRUD**，带连接池管理：

### User 表结构
```sql
CREATE TABLE users (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(64) NOT NULL,
  email VARCHAR(128),
  age INT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 统一 CRUD 接口
```bash
# 创建
POST /users
{"name": "Alice", "email": "a@x.com", "age": 28}
→ {"id": 1, "name": "Alice", ...}

# 查询
GET /users/{id}
→ {"id": 1, ...}

# 列表
GET /users?page=1&size=10
→ {"items": [...], "total": 100}

# 更新
PUT /users/{id}
{"name": "Alice 2.0"}

# 删除
DELETE /users/{id}
```

> ⚠️ **需要本地 MySQL 环境**，可以用 Docker 快速拉起：`docker run -e MYSQL_ROOT_PASSWORD=root -p 3306:3306 mysql:8`

所有语言实现**业务逻辑完全一致**。

---

## 实现清单

| 语言 | 数据访问层 | 连接池 | 亮点 |
|------|-----------|--------|------|
| Java | MyBatis / Spring Data JPA | HikariCP（Spring Boot 默认） | 成熟生态，PageHelper 分页 |
| Go | `database/sql` + GORM | `database/sql` 内置池 | GORM 链式 API |
| Python | SQLAlchemy 2.0 async + aio_pymysql | SQLAlchemy async pool | async 支持好 |
| Rust | **sqlx** | sqlx 内置池 | ⭐ **编译期 SQL 校验**（最大差异化） |
| TS(Node) | **Prisma** | Prisma 内置池 | 类型安全 ORM，原生 TS 类型 |

### 特别关注
- **Rust sqlx 编译期校验**：SQL 语法、类型、表结构在编译时验证 — 这是 Java 工程师最感兴趣的特性
- **Java HikariCP**：业界最快连接池
- **Prisma**：TS 世界的类型安全 ORM 代表
- **GORM**：Go 生态最流行的 ORM

---

## 关键对比

| 维度 | Java | Go | Python | Rust | TS(Node) |
|------|------|----|--------|------|----------|
| **端口** | 8125 | 8126 | 8127 | 8128 | 8129 |
| **数据库** | SQLite (jdbc) | SQLite (glebarez/sqlite) | SQLite | SQLite | SQLite (better-sqlite3) |
| **ORM / 数据层** | Spring Data JPA | GORM | SQLAlchemy 2.0 | sqlx（手写 SQL） | better-sqlite3（手写 SQL） |
| **SQL 类型安全** | ❌ 运行时 Hibernate 生成 SQL | ❌ GORM 运行时拼接 | ❌ SQLAlchemy 表达式运行时 | ⭐⭐⭐⭐⭐ **sqlx FromRow 编译期安全** | ❌ better-sqlite3 纯字符串 |
| **连接池** | ✅ HikariCP（Spring Boot 默认） | ✅ database/sql 内置 | ✅ SQLAlchemy QueuePool | ✅ SqlitePool | ❌ Node 单线程不需要！ |
| **最大连接数** | maximum-pool-size=10 | SetMaxOpenConns(10) | pool_size=10 | max_connections(10) | N/A（单线程） |
| **自动建表** | ✅ ddl-auto=update | ✅ GORM AutoMigrate | ✅ Base.metadata.create_all | ✅ CREATE TABLE IF NOT EXISTS | ✅ CREATE TABLE IF NOT EXISTS |
| **分页实现** | PageRequest | Offset + Limit | query.offset().limit() | LIMIT ? OFFSET ? | LIMIT ? OFFSET ? |
| **事务** | ✅ @Transactional | ✅ db.Begin() / Commit() | ✅ with Session: | ✅ pool.begin().await | ✅ db.transaction() |
| **编译期 SQL 校验** | ❌ | ❌ | ❌ | ⭐⭐⭐⭐⭐ **sqlx 宏可选（需真实 DB）** | ❌ |
| **DDL / Schema 迁移** | Hibernate ddl-auto / Flyway / Liquibase | GORM AutoMigrate | Alembic（外部） | 手写 SQL / sqlx-cli migrate | Prisma migrate / 手写 |
| **同步/异步** | 同步（JPA 默认） | 同步 | async / sync 都支持 | async（tokio） | **同步（Node 单线程 + better-sqlite3 同步高效）** |
| **零外部依赖** | ❌ Spring Data JPA + SQLite JDBC | ⚠️ GORM + SQLite 驱动 | ⚠️ SQLAlchemy 2.0 | ❌ sqlx + tokio + axum | ⚠️ better-sqlite3 原生模块 |
| **代码行数（含 CRUD）** | ~200 行（entity + repo + controller） | ~220 行 | ~200 行 | ~230 行 | ~180 行 |
| **优势** | Spring Data JPA 零实现代码、HikariCP 业界最快 | GORM 链式 API、标准库连接池 | SQLAlchemy 功能最全、async 支持好 | **sqlx 类型安全**（最大亮点） | Node 单线程同步最简单 |
| **痛点 & 坑** | JPA 生成 SQL 黑盒、复杂查询 NativeQuery 难用 | GORM 复杂查询失控、SQLite 驱动要选 | SQLAlchemy 2.0 学习曲线陡峭 | sqlx 宏需要真实 DB 连接编译、Cargo 下载慢 | better-sqlite3 原生编译有坑、不支持 Windows ARM |

---

## 选型思考

### 五种 DB 访问层定位

| 场景 | 推荐 | 原因 |
|------|------|------|
| **Java/Spring Boot** | ★ Spring Data JPA + HikariCP | 零实现代码、HikariCP 业界最快、生态成熟 |
| **Go 微服务** | 🐹 GORM（简单）或 database/sql（精细） | GORM 链式 API 快；database/sql 可控性高 |
| **Python 数据/AI** | 🐍 SQLAlchemy 2.0 + async | Python 最成熟、功能最全、支持 sync/async |
| **Rust 高性能** | 🦀 sqlx | **类型安全**是绝杀、SQL 运行时性能碾压 |
| **Node/BFF 层** | 🟦 Prisma（类型安全 ORM）或 better-sqlite3 | Prisma 生成 TS 类型；better-sqlite3 最轻 |

### 关键选型决策点

| 问题 | 答案 |
|------|------|
| **SQL 能否编译期校验？** | 只有 **Rust sqlx** 能（其他语言运行时才知道 SQL 对不对） |
| **要类型安全 ORM？** | Prisma（TS）/ sqlx（Rust）/ Spring Data JPA（Java 注解） |
| **连接池配置？** | 全都支持，参数名略有不同 |
| **分布式？** | 换 MySQL/PostgreSQL，sqlx/Prism/GORM 都支持切换 |
| **轻量 demo？** | SQLite 零依赖本地文件 ✅ 本次用的方案 |

## 运行方式

<!-- TODO: 实现后补充启动/运行命令 -->

### Java
```bash
# TODO (需要本地 MySQL)
```

### Go
```bash
# TODO (需要本地 MySQL)
```

### Python
```bash
# TODO (需要本地 MySQL)
```

### Rust
```bash
# TODO (需要本地 MySQL，sqlx 编译时需要 DB 连接)
```

### TS(Node)
```bash
# TODO (需要本地 MySQL)
```

---

## 选型思考

<!-- TODO: 实现后补充选型建议 -->

