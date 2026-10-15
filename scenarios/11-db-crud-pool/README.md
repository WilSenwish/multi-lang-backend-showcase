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
| **ORM vs 原生 SQL** | | | | | |
| **SQL 类型安全** | | | | | |
| **连接池实现** | | | | | |
| **事务** | | | | | |
| **分页** | | | | | |
| **优势** | | | | | |
| **痛点 & 坑** | | | | | |

---

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

