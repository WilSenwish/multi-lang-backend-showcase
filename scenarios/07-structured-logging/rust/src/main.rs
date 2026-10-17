//! 场景 07：结构化日志 — Rust 实现（tracing + tracing-subscriber）
//!
//! Rust 结构化日志特点：
//! 1. tracing 是 Rust 生态事实标准（不是日志库本身，是 API 层）
//! 2. tracing-subscriber 是实现层，负责格式化输出（json/env-filter 等 feature）
//! 3. tracing-json encoder 输出结构化 JSON
//! 4. 编译期字段检查！info!(requestId = "abc", "msg"); 里的 requestId 是编译期确定的
//! 5. span 嵌套：进入请求时进入 span，后续所有日志自动带上 span 字段（类似 Java MDC）
//! 6. tracing-error 可以把 Result 的错误嵌入 span 的 error 字段
//!
//! 和其他语言对比：
//! - tracing 宏本身零运行时开销（编译期展开）
//! - 错误链：可以用 tracing::error!(error = ?e) 嵌入 Debug 或 Display
//! - Span 树可视化（tracing-viewer）是一大优势

use axum::{
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::get,
    Router,
};
use serde::Serialize;
use std::time::Instant;
use tracing::{error, info, info_span};
use tracing_subscriber::{fmt, EnvFilter};
use uuid::Uuid;

// ==================== 端点 ====================

async fn ping() -> impl axum::response::IntoResponse {
    let start = Instant::now();
    let request_id = Uuid::new_v4().to_string()[..8].to_string();

    // 进入 span → 后续所有日志自动带上 requestId, userId, path
    let span = info_span!("ping_handler", requestId = %request_id, userId = "anonymous", path = "/ping");
    let _guard = span.enter();

    info!("ping request handled");
    // as u64：u128 会被 tracing 的 JSON 渲染成字符串 "0"，与其余四门的数字类型不一致
    info!(costMs = start.elapsed().as_millis() as u64, "request completed");

    axum::Json(serde_json::json!({"pong": true, "request_id": request_id}))
}

async fn debug() -> impl axum::response::IntoResponse {
    let request_id = Uuid::new_v4().to_string()[..8].to_string();
    let span = info_span!("debug_handler", requestId = %request_id, userId = "debug-user", path = "/debug");
    let _guard = span.enter();

    // 消息与级别与其余四门对齐：INFO "debug endpoint hit"
    // （之前用 warn! 且消息带后缀，跨语言不一致）
    info!("debug endpoint hit");

    axum::Json(serde_json::json!({"debug": true, "request_id": request_id}))
}

async fn error_endpoint() -> impl axum::response::IntoResponse {
    let request_id = Uuid::new_v4().to_string()[..8].to_string();
    let span = info_span!("error_handler", requestId = %request_id, userId = "error-user", path = "/error");
    let _guard = span.enter();

    // 模拟错误
    let err = Err::<String, _>(String::from("nil pointer dereference on 'nullStr'"));
    match err {
        Ok(_) => unreachable!(),
        Err(ref e) => {
            // tracing 的 error! 宏可以直接嵌入 error 字段
            error!(
                costMs = 150,
                errorCode = "NULL_POINTER",
                error = %e,    // Display：错误消息
                error_debug = ?e, // Debug：完整错误结构
                "request failed with exception"
            );
        }
    }

    axum::Json(serde_json::json!({"error": "simulated"}))
}

async fn bench(axum::extract::Query(params): axum::extract::Query<BenchParams>) -> Response {
    // count 缺省 1000；非数字 / < 1 都是客户端错误 → 400
    // （之前 count=0 会在这里做除零 panic，直接被连接重置）
    let count = match params.count {
        None => 1000,
        Some(0) => {
            return (StatusCode::BAD_REQUEST, "count must be >= 1").into_response();
        }
        Some(n) => n,
    };
    let request_id = Uuid::new_v4().to_string()[..8].to_string();
    let span = info_span!("bench_handler", requestId = %request_id, userId = "bench-user", path = "/bench");
    let _guard = span.enter();

    let start = Instant::now();
    for i in 0..count {
        info!(index = i, total = count, "benchmark log entry");
    }
    let cost = start.elapsed();
    let avg_ns = cost.as_nanos() / count as u128;

    info!(count = count, totalCostMs = cost.as_millis() as u64, avgLogNs = avg_ns as u64, "benchmark completed");

    axum::Json(serde_json::json!({
        "count": count,
        "total_cost_ms": cost.as_millis(),
        "avg_log_ns": avg_ns as u64,
        "request_id": request_id,
    }))
    .into_response()
}

#[derive(serde::Deserialize)]
struct BenchParams {
    /// 缺省 None → 1000；显式传值（含 0）必须 >= 1
    count: Option<u32>,
}

// ==================== main ====================

#[tokio::main]
async fn main() {
    // 初始化 tracing-subscriber：JSON 格式到 stdout
    tracing_subscriber::fmt()
        .with_env_filter(
            EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| EnvFilter::new("info")),
        )
        .json()                         // JSON 格式输出
        .with_target(true)              // 显示 target（模块路径）
        .with_file(true)                // 显示源文件名
        .with_line_number(true)         // 显示行号
        .with_level(true)               // 显示级别
        .with_current_span(true)        // 把 span 名和字段嵌入每条日志
        .init();

    // 应用启动日志
    let span = info_span!("server_start", addr = "0.0.0.0:8108", app = "structured-logging-rust");
    let _guard = span.enter();
    info!(addr = "0.0.0.0:8108", mode = "prod", "server starting");

    let app = Router::new()
        .route("/ping", get(ping))
        .route("/debug", get(debug))
        .route("/error", get(error_endpoint))
        .route("/bench", get(bench));

    let listener = tokio::net::TcpListener::bind("0.0.0.0:8108").await.unwrap();
    axum::serve(listener, app).await.unwrap();
}
