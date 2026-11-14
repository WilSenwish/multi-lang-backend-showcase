//! 场景 12：优雅关闭 — Rust 实现（axum + tokio）
//!
//! Rust 优雅关闭特点：
//! 1. tokio::signal::ctrl_c() / tokio::signal::unix::signal(SIGTERM) 捕获信号
//! 2. axum::serve() 返回 Serve 结构体，有 .graceful_shutdown(shutdown_signal) 方法
//! 3. shutdown_signal 是 async fn，可在这里等待资源释放
//! 4. tokio::spawn 所有清理任务，确保关闭时等待它们完成
//!
//! 和 Go 对比：
//! - Go 一行 signal.NotifyContext() 更简洁
//! - Rust 用 async 函数作为 shutdown_signal 更显式
//! - 两者设计都很优雅

use axum::{
    extract::State,
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::{get},
    Router,
};
use serde::{Deserialize, Serialize};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;
use std::time::Duration;
use tokio::signal;
use tokio::sync::watch;

// ==================== 全局状态 ====================

struct AppState {
    in_flight: AtomicUsize,
    shutting_down: Arc<std::sync::atomic::AtomicBool>,
}

// ==================== Handler ====================

async fn long_task(State(state): State<Arc<AppState>>) -> Response {
    let id = state.in_flight.fetch_add(1, Ordering::SeqCst);
    let in_flight = state.in_flight.load(Ordering::SeqCst);
    tracing::debug!(req_id = id, in_flight, "start processing long-task");

    // 模拟 3s 耗时（tokio sleep 不阻塞事件循环）
    tokio::time::sleep(Duration::from_secs(3)).await;

    state.in_flight.fetch_sub(1, Ordering::SeqCst);
    tracing::debug!(req_id = id, "finished long-task");

    axum::Json(serde_json::json!({
        "ok": true,
        "duration_ms": 3000,
        "shutting_down": state.shutting_down.load(Ordering::SeqCst),
    }))
    .into_response()
}

async fn health(State(state): State<Arc<AppState>>) -> Response {
    let body = serde_json::json!({
        "service": "graceful-shutdown-rust",
        "shutting_down": state.shutting_down.load(Ordering::SeqCst),
        "in_flight": state.in_flight.load(Ordering::SeqCst),
    });

    let status = if state.shutting_down.load(Ordering::SeqCst) {
        StatusCode::SERVICE_UNAVAILABLE
    } else {
        StatusCode::OK
    };

    (status, axum::Json(body)).into_response()
}

// ==================== main ====================

#[tokio::main]
async fn main() {
    // 初始化 tracing 日志：JSON 格式 + 最低 DEBUG 级别 + stdout
    tracing_subscriber::fmt()
        .with_env_filter(tracing_subscriber::EnvFilter::try_from_default_env()
            .unwrap_or_else(|_| "debug".into()))
        .with_target(false)
        .json()
        .init();

    tracing::info!("=== scene 12: graceful shutdown — Rust impl (axum + tokio) ===");
    tracing::info!("signal: kill -TERM <pid> or Ctrl+C");

    let state = Arc::new(AppState {
        in_flight: AtomicUsize::new(0),
        shutting_down: Arc::new(std::sync::atomic::AtomicBool::new(false)),
    });

    // 构建路由
    let app = Router::new()
        .route("/api/long-task", get(long_task))
        .route("/api/health", get(health))
        .with_state(state.clone());

    // 启动 HTTP 服务
    let listener = tokio::net::TcpListener::bind("0.0.0.0:8133").await.unwrap();
    tracing::info!(addr = "0.0.0.0:8133", "server starting");

    let server = axum::serve(listener, app);

    // ============ 优雅关闭核心 ============
    // 捕获信号（Ctrl+C 或 SIGTERM）
    // 信号闭包需 move 一份 state 克隆（state 在关闭块之后仍要使用）
    let shutdown_state = state.clone();
    let shutdown_signal = async move {
        // 监听 Ctrl+C
        let ctrl_c = async {
            signal::ctrl_c().await.expect("failed to install Ctrl+C handler");
        };

        // 监听 SIGTERM
        #[cfg(unix)]
        let sigterm = async {
            signal::unix::signal(signal::unix::SignalKind::terminate())
                .expect("failed to install SIGTERM handler")
                .recv()
                .await;
        };

        #[cfg(not(unix))]
        let sigterm = std::future::pending::<()>();

        tokio::select! {
            _ = ctrl_c => {},
            _ = sigterm => {},
        }

        tracing::info!("=== graceful shutdown: signal received ===");
        tracing::info!("=== step 1/4: mark shutting_down=true ===");
        shutdown_state.shutting_down.store(true, Ordering::SeqCst);
    };

    // axum 优雅关闭
    server
        .with_graceful_shutdown(shutdown_signal)
        .await
        .expect("server error");

    // 等待 in-flight 请求完成（超时 10s）
    tracing::info!("=== step 2/4: stop accepting new requests ===");
    tracing::info!("=== step 3/4: waiting for in-flight requests (timeout=10s) ===");

    let start = std::time::Instant::now();
    let timeout = Duration::from_secs(10);
    loop {
        let in_flight = state.in_flight.load(Ordering::SeqCst);
        if in_flight == 0 {
            tracing::info!("=== all requests completed ===");
            break;
        }
        if start.elapsed() >= timeout {
            tracing::warn!(remaining = in_flight, "timeout! requests still pending");
            break;
        }
        tracing::debug!(remaining = in_flight, "waiting for requests to complete");
        tokio::time::sleep(Duration::from_millis(200)).await;
    }

    tracing::info!("=== step 4/4: release resources ===");
    tracing::info!("=== shutdown complete ===");
}
