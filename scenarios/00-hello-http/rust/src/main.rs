//! scenarios/00-hello-http Rust 实现 (axum + serde + tokio)
//!
//! 统一 API 契约:
//!     GET /hello?name={xxx}
//!     → {"msg": "hello {xxx}"}
//!     → {"msg": "hello world"}  // name 缺省

use axum::{extract::Query, routing::get, Json, Router};
use serde::Serialize;
use std::net::SocketAddr;

/// 统一响应 DTO
#[derive(Serialize)]
struct HelloResponse {
    msg: String,
}

/// 查询参数结构体
#[derive(Debug, serde::Deserialize)]
struct HelloQuery {
    name: Option<String>,
}

const DEFAULT_NAME: &str = "world";
const LISTEN_ADDR: &str = "0.0.0.0:8083";

async fn hello(Query(query): Query<HelloQuery>) -> Json<HelloResponse> {
    let target = query.name.as_deref().filter(|s| !s.is_empty()).unwrap_or(DEFAULT_NAME);
    Json(HelloResponse {
        msg: format!("hello {}", target),
    })
}

#[tokio::main]
async fn main() {
    // 初始化 tracing 日志：JSON 格式 + 最低 DEBUG 级别 + stdout
    tracing_subscriber::fmt()
        .with_env_filter(tracing_subscriber::EnvFilter::try_from_default_env()
            .unwrap_or_else(|_| "debug".into()))
        .with_target(false)
        .json()
        .init();

    let app = Router::new().route("/hello", get(hello));

    let addr: SocketAddr = LISTEN_ADDR.parse().expect("invalid address");
    tracing::info!(addr = %addr, "server starting");

    let listener = tokio::net::TcpListener::bind(addr)
        .await
        .expect("failed to bind address");
    axum::serve(listener, app).await.expect("server error");
}
