# 场景 11：SQLite CRUD + 连接池

## 业务描述

统一实现简单的 **User 表 CRUD**，带连接池管理：

### User 表结构

> 五种语言建表结果一致，下表为 SQLite 实际 DDL（Rust / TS 为手写 `CREATE TABLE IF NOT EXISTS`，
> Java / Go / Python 分别由 Hibernate `ddl-auto`、GORM `AutoMigrate`、`Base.metadata.create_all` 生成等价结构）。

```sql
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  email TEXT,
  age INTEGER,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
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

> ✅ **零外部依赖**：本场景全部使用 **SQLite 本地文件**，不需要安装或启动任何数据库服务。
> 各语言的库文件由首次启动时自动建表生成，且**已被 `.gitignore` 排除，不会入库**：
> `go/demo.db`、`java/demo.db`、`python/demo_py.db`、`rust/demo_rs.db`、`ts-node/demo_ts.db{,-shm,-wal}`。
> 想重置数据，直接删掉对应 `.db` 文件重启即可。

> ⚠️ 唯一需要额外准备的：TS-Node 用的 `better-sqlite3` 是**原生模块**，官方未提供 Node v24 的预编译产物，
> 需先执行 `npm rebuild better-sqlite3 --build-from-source`（详见下方「运行方式 → TS(Node)」）。

所有语言实现**业务逻辑完全一致**。

---

## 实现清单

| 语言 | 数据访问层 | 连接池 | 亮点 |
|------|-----------|--------|------|
| Java | Spring Data JPA + `sqlite-jdbc` + `hibernate-community-dialects` | HikariCP（Spring Boot 默认） | 零实现代码，方法名即查询 |
| Go | GORM + `glebarez/sqlite`（纯 Go 驱动） | GORM 底层 `database/sql` 内置池 | GORM 链式 API + `AutoMigrate` |
| Python | SQLAlchemy 2.0（同步） | `NullPool`（SQLite 单文件无需真连接池） | 表达式构造能力强，async/sync 双支持 |
| Rust | **sqlx** + `SqlitePoolOptions` | sqlx 内置 `SqlitePool` | ⭐ `FromRow` 编译期类型绑定（最大差异化） |
| TS(Node) | **better-sqlite3**（手写 SQL） | 不需要（Node 单线程，同步驱动） | 同步 API 最简单，无回调地狱 |

### 特别关注
- **Rust sqlx 的类型安全**：`FromRow` 把查询结果在**编译期**绑定到结构体，字段类型不匹配直接编译失败 —
  这是 Java 工程师最感兴趣的特性（JPA 要等运行时才知道 SQL 对不对）
- **Java HikariCP**：业界最快连接池；但 SQLite 是单文件数据库，本场景连接池更多是"配置演示"而非"性能刚需"
- **Python 的 `NullPool`**：SQLite 场景下 SQLAlchemy 默认就建议关掉连接池，这是与其余四门语言最不一样的地方
- **Node 没有连接池**：`better-sqlite3` 是**同步**驱动，Node 单线程下"一个连接"就是最优解，套连接池反而多余
- **GORM**：Go 生态最流行的 ORM，`AutoMigrate` 一把梭建表

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

## 契约要点（验证强度加强计划批次 5）

场景 11 已在批次 5（2026-10-17）从「端口监听级」升级为**契约级断言**（`verify_11`），
`python3 .wb_verify/verify_all.py 11` → **5/5 全绿**。契约覆盖五道关：

- **健康检查**：`/health` 必须 200 且返回 `{service, db}`（专门抓 Java 原先缺 `/health` 端点）。
- **CRUD 全链路**：POST 返回 **201**（非 200）且 body 含 `id`（正整数）/ `name` / `age` / `created_at`；
  GET/PUT 路由 200；DELETE 返回 **204** 且删后再 GET 该 id 必须 **404**；GET 不存在的 id 必须 404。
- **`created_at` 必须 snake_case**：专门抓 Java Jackson 默认 camelCase（`createdAt`）的序列化漂移 ——
  与场景 02 同款坑，靠 `spring.jackson.property-naming-strategy=SNAKE_CASE` 一次性修掉。
- **分页自洽**：`GET /users?page=0&size=3` 的响应 `items` 长度 ≤ size、`page`/`size` 回显一致、`total` 为整数。
- **错误码不得落到 500**：`name` 缺失必须返 400（不得 500）；`page=abc`（`Number()` 得 NaN）必须返 400（不得 500）。

> ⚠️ **实现坑（已在批次 5 修复）**：
> - **Go**：路由必须用通配符 `/users/{id}`，写 `/users/`（子树匹配）会让 `r.PathValue("id")` 恒为空、所有带 id 的请求 400。
> - **Rust（axum 0.7 + matchit 0.7.3）**：路径参数**只认 `:id` 冒号语法**，写 `{id}` 直接 404。
> - **Java**：缺 `/health` 端点、`createdAt` 默认 camelCase、POST 返回 200 而非 201、`name` 缺失抛 500 —— 四处一并修。
> - **TS(Node)**：`better-sqlite3` 在 `name` 缺失时 INSERT 抛错、`page=abc` 时 `Number()` 得 NaN（`SQLITE_MISMATCH`）—— 两者都会落到 500，需显式 400 拦截。
> - **Python**：经探针实测已正确（201 / snake_case / `name` 缺失返 422 非 500），无需改动。

---

## 选型思考

### 五种 DB 访问层定位

| 场景 | 推荐 | 原因 |
|------|------|------|
| **Java/Spring Boot** | ★ Spring Data JPA + HikariCP | 零实现代码、HikariCP 业界最快、生态成熟 |
| **Go 微服务** | 🐹 GORM（简单）或 database/sql（精细） | GORM 链式 API 快；database/sql 可控性高 |
| **Python 数据/AI** | 🐍 SQLAlchemy 2.0 + async | Python 最成熟、功能最全、支持 sync/async |
| **Rust 高性能** | 🦀 sqlx | **类型安全**是绝杀、SQL 运行时性能碾压 |
| **Node/BFF 层** | 🟦 Prisma（类型安全 ORM）或 better-sqlite3 | Prisma 生成 TS 类型；better-sqlite3 最轻（**本仓库用的是后者**） |

### 关键选型决策点

| 问题 | 答案 |
|------|------|
| **SQL 能否编译期校验？** | 只有 **Rust sqlx** 能（其他语言运行时才知道 SQL 对不对） |
| **要类型安全 ORM？** | Prisma（TS）/ sqlx（Rust）/ Spring Data JPA（Java 注解） |
| **连接池配置？** | 全都支持，参数名略有不同 |
| **分布式？** | 换 MySQL/PostgreSQL，sqlx/Prisma/GORM 都支持切换 |
| **轻量 demo？** | SQLite 零依赖本地文件 ✅ 本次用的方案 |

### 从 SQLite 迁到 MySQL / PostgreSQL 要改什么

本场景选 SQLite 是为了**零外部依赖**（clone 下来就能跑）。真上生产换 MySQL/PostgreSQL 时，五门语言的改动量不同：

| 语言 | 改动点 | 代价 |
|------|--------|------|
| Java | 换 JDBC 驱动 + `spring.datasource.*`；Hibernate 方言自动识别 | 小（JPA 屏蔽了差异） |
| Go | 换驱动包（`gorm.io/driver/mysql`）+ DSN | 小 |
| Python | 换驱动 + DSN；`NullPool` 要改回 `QueuePool` | 小，但**连接池语义要重新调** |
| Rust | 换 sqlx feature + DSN；`query_as` 不变 | 小（类型安全仍在） |
| TS(Node) | `better-sqlite3` 是 SQLite 专用，需整层换成 `mysql2`/`pg` | **大**（同步 API 变异步，业务代码全改） |

> 这也说明：**选型时"数据库无关性"本身就是一项能力**。JPA / GORM / SQLAlchemy / sqlx 都把驱动差异收敛在配置层，
> 而 Node 选了 `better-sqlite3` 这种"贴着数据库特性设计"的库，换库成本就高得多。

## 运行方式

> 五门语言端口连续分配：**Java 8125 / Go 8126 / Python 8127 / Rust 8128 / TS-Node 8129**。
> 首次启动会自动建表并生成对应的 `.db` 文件，无需手工初始化。

### Java（端口 8125）

```bash
cd java
mvn spring-boot:run
# 或打包后运行：mvn clean package -DskipTests && java -jar target/db-crud-pool-1.0.0.jar
```

### Go（端口 8126）

```bash
cd go
export GOPROXY=https://goproxy.cn,direct GOSUMDB=off   # 国内网络建议设置
go run .
```

### Python（端口 8127）

```bash
cd python
pip install -r requirements.txt   # fastapi / uvicorn / pydantic / sqlalchemy
python main.py
```

### Rust（端口 8128）

```bash
cd rust
cargo run --release
```

> `Cargo.lock` 被 `.gitignore` 忽略（库项目惯例），首次编译会重新解析依赖版本。

### TS(Node)（端口 8129）

```bash
cd ts-node
npm install
# better-sqlite3 是原生模块，官方无 Node v24 预编译产物，必须源码构建一次：
npm rebuild better-sqlite3 --build-from-source
npm run dev        # 或 npm run build && npm start
```

> ⚠️ 原生模块与 Node ABI 绑定：上面构建出的产物**只对同 ABI 的 Node 有效**。
> 换用其它大版本 Node（如 v22）会重新报 `Could not locate the bindings file`，需要重建。

### 统一验证

```bash
# 健康检查（5 个端口返回结构一致）
curl localhost:8125/health && curl localhost:8126/health && curl localhost:8127/health \
  && curl localhost:8128/health && curl localhost:8129/health

# 写入 → 读取（换成任意端口即可横向对比）
curl -X POST localhost:8126/users -H 'Content-Type: application/json' \
  -d '{"name":"Alice","email":"a@x.com","age":28}'
curl localhost:8126/users/1
curl 'localhost:8126/users?page=0&size=10'
curl -X PUT localhost:8126/users/1 -H 'Content-Type: application/json' -d '{"name":"Alice 2.0"}'
curl -X DELETE localhost:8126/users/1
```

### 统一 API 契约

| 方法 | 路径 | 说明 | 成功响应 |
|------|------|------|---------|
| `POST` | `/users` | 创建 | `201` + 完整 User |
| `GET` | `/users/{id}` | 查询单个 | `200` + 完整 User |
| `GET` | `/users?page=0&size=10` | 分页列表 | `200` + `{items, total, page, size}` |
| `PUT` | `/users/{id}` | 更新（全量） | `200` + 更新后 User |
| `DELETE` | `/users/{id}` | 删除 | `204` 无 body |
| `GET` | `/health` | 健康检查 | `200` + `{service, db}` |

---
