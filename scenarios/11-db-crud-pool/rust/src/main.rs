//! 场景 11：数据库 CRUD + 连接池 — Rust 实现（sqlx + SQLite）
//!
//! ⭐ **核心亮点：sqlx 的类型安全 SQL**
//!
//! 和其他语言对比的最大差异化：
//! - Rust sqlx 的 `sqlx::query_as::<_, User>()` 返回值是 **编译期类型检查的**
//!   类型错了直接编译不过！这是 Java/Python/Go/TS ORM 都做不到的。
//!
//! 连接池：SqlitePool 内置，max_connections/min_connections 可配置

use axum::{
    extract::{Path, Query, State, Json as AxumJson},
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::{get, post, put, delete},
    Router,
};
use serde::{Deserialize, Serialize};
use sqlx::{sqlite::SqlitePoolOptions, FromRow, SqlitePool};
use std::sync::Arc;
use std::time::Duration;

// ==================== 数据结构 ====================

#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct User {
    pub id: i64,
    pub name: String,
    pub email: Option<String>,
    pub age: Option<i64>,
    #[serde(rename = "created_at")]
    pub created_at: Option<String>,
}

#[derive(Debug, Deserialize)]
struct UserCreate {
    name: String,
    email: Option<String>,
    age: Option<i64>,
}

#[derive(Debug, Deserialize)]
struct UserUpdate {
    name: Option<String>,
    email: Option<String>,
    age: Option<i64>,
}

#[derive(Debug, Deserialize)]
struct ListQuery {
    page: Option<u32>,
    size: Option<u32>,
}

// ==================== DB 初始化 ====================

async fn init_db() -> SqlitePool {
    let pool = SqlitePoolOptions::new()
        .max_connections(10)
        .min_connections(2)
        .acquire_timeout(Duration::from_secs(5))
        .connect("sqlite://demo_rs.db?mode=rwc")
        .await
        .expect("SQLite 连接失败");

    // 自动建表
    sqlx::query(
        "CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT,
            age INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"
    )
    .execute(&pool)
    .await
    .expect("建表失败");

    println!("[Rust] DB 初始化成功（SQLite: demo_rs.db）");
    pool
}

// ==================== CRUD ====================

type AppState = Arc<SqlitePool>;

// CREATE
async fn create_user(
    State(pool): State<AppState>,
    AxumJson(input): AxumJson<UserCreate>,
) -> Response {
    let row = sqlx::query_as::<_, User>(
        "INSERT INTO users (name, email, age) VALUES (?, ?, ?) RETURNING *"
    )
    .bind(&input.name)
    .bind(&input.email)
    .bind(input.age)
    .fetch_one(pool.as_ref())
    .await;

    match row {
        Ok(user) => (StatusCode::CREATED, axum::Json(user)).into_response(),
        Err(e) => (StatusCode::BAD_REQUEST, axum::Json(serde_json::json!({"error": e.to_string()}))).into_response(),
    }
}

// READ ONE
async fn get_user(
    State(pool): State<AppState>,
    Path(id): Path<i64>,
) -> Response {
    let row = sqlx::query_as::<_, User>(
        "SELECT id, name, email, age, created_at FROM users WHERE id = ?"
    )
    .bind(id)
    .fetch_optional(pool.as_ref())
    .await;

    match row {
        Ok(Some(user)) => axum::Json(user).into_response(),
        Ok(None) => StatusCode::NOT_FOUND.into_response(),
        Err(e) => (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()).into_response(),
    }
}

// LIST
async fn list_users(
    State(pool): State<AppState>,
    Query(q): Query<ListQuery>,
) -> Response {
    let page = q.page.unwrap_or(0);
    let size = q.size.unwrap_or(10);
    let offset = (page * size) as i64;
    let limit = size as i64;

    // 总数
    let row: (i64,) = sqlx::query_as("SELECT COUNT(*) FROM users")
        .fetch_one(pool.as_ref())
        .await
        .unwrap_or((0,));

    // 分页
    let items = sqlx::query_as::<_, User>(
        "SELECT id, name, email, age, created_at FROM users ORDER BY id ASC LIMIT ? OFFSET ?"
    )
    .bind(limit)
    .bind(offset)
    .fetch_all(pool.as_ref())
    .await
    .unwrap_or_default();

    axum::Json(serde_json::json!({
        "items": items,
        "total": row.0,
        "page": page,
        "size": size,
    }))
    .into_response()
}

// UPDATE
async fn update_user(
    State(pool): State<AppState>,
    Path(id): Path<i64>,
    AxumJson(input): AxumJson<UserUpdate>,
) -> Response {
    // 查存在性
    let exists = sqlx::query_as::<_, (i64,)>("SELECT id FROM users WHERE id = ?")
        .bind(id)
        .fetch_optional(pool.as_ref())
        .await;

    match exists {
        Ok(None) => return StatusCode::NOT_FOUND.into_response(),
        Ok(_) => {}
        Err(e) => return (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()).into_response(),
    }

    // 更新每个有值的字段
    if let Some(ref name) = input.name {
        let _ = sqlx::query("UPDATE users SET name = ? WHERE id = ?")
            .bind(name)
            .bind(id)
            .execute(pool.as_ref())
            .await;
    }
    if input.email.is_some() {
        let _ = sqlx::query("UPDATE users SET email = ? WHERE id = ?")
            .bind(input.email.as_ref())
            .bind(id)
            .execute(pool.as_ref())
            .await;
    }
    if let Some(age) = input.age {
        let _ = sqlx::query("UPDATE users SET age = ? WHERE id = ?")
            .bind(age)
            .bind(id)
            .execute(pool.as_ref())
            .await;
    }

    // 返回更新后
    let updated = sqlx::query_as::<_, User>(
        "SELECT id, name, email, age, created_at FROM users WHERE id = ?"
    )
    .bind(id)
    .fetch_one(pool.as_ref())
    .await
    .unwrap();

    axum::Json(updated).into_response()
}

// DELETE
async fn delete_user(
    State(pool): State<AppState>,
    Path(id): Path<i64>,
) -> Response {
    let result = sqlx::query("DELETE FROM users WHERE id = ?")
        .bind(id)
        .execute(pool.as_ref())
        .await;

    match result {
        Ok(r) if r.rows_affected() == 0 => StatusCode::NOT_FOUND.into_response(),
        Ok(_) => StatusCode::NO_CONTENT.into_response(),
        Err(e) => (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()).into_response(),
    }
}

// ==================== main ====================

#[tokio::main]
async fn main() {
    println!("DB CRUD + 连接池 — Rust sqlx 实现");
    println!("核心亮点：sqlx 返回值编译期类型安全（FromRow trait）");

    let pool = init_db().await;
    let app = Router::new()
        .route("/users", post(create_user).get(list_users))
        .route("/users/:id", get(get_user).put(update_user).delete(delete_user))
        .route("/health", get(|| async { axum::Json(serde_json::json!({"service": "db-crud-pool-rust", "db": "sqlite (sqlx)"})) }))
        .with_state(Arc::new(pool));

    let listener = tokio::net::TcpListener::bind("0.0.0.0:8128").await.unwrap();
    println!("[Rust] db-crud-pool server starting on 0.0.0.0:8128");
    axum::serve(listener, app).await.unwrap();
}
