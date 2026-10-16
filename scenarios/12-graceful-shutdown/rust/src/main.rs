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
    println!("[REQUEST] 开始处理 long-task, id={}, in-flight={}", id, in_flight);

    // 模拟 3s 耗时（tokio sleep 不阻塞事件循环）
    tokio::time::sleep(Duration::from_secs(3)).await;

    state.in_flight.fetch_sub(1, Ordering::SeqCst);
    println!("[REQUEST] 完成 long-task, id={}", id);

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
    println!("========================================");
    println!("场景 12：优雅关闭 — Rust 实现（axum + tokio）");
    println!("信号：kill -TERM <pid> 或 Ctrl+C");
    println!("========================================");

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
    println!("[Rust] server starting on 0.0.0.0:8133");

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

        println!("========================================");
        println!("[GRACEFUL SHUTDOWN] 收到关闭信号");
        println!("[GRACEFUL SHUTDOWN] Step 1/4: 标记 shutting_down=true");
        shutdown_state.shutting_down.store(true, Ordering::SeqCst);
    };

    // axum 优雅关闭
    server
        .with_graceful_shutdown(shutdown_signal)
        .await
        .expect("server error");

    // 等待 in-flight 请求完成（超时 10s）
    println!("[GRACEFUL SHUTDOWN] Step 2/4: 停止接收新请求");
    println!("[GRACEFUL SHUTDOWN] Step 3/4: 等待 in-flight 请求完成 (timeout=10s)");

    let start = std::time::Instant::now();
    let timeout = Duration::from_secs(10);
    loop {
        let in_flight = state.in_flight.load(Ordering::SeqCst);
        if in_flight == 0 {
            println!("[GRACEFUL SHUTDOWN] ✅ 所有请求完成");
            break;
        }
        if start.elapsed() >= timeout {
            println!("[GRACEFUL SHUTDOWN] ⚠️ 超时！还有 {} 个请求未完成", in_flight);
            break;
        }
        println!("[GRACEFUL SHUTDOWN]   等待 {} 个请求完成...", in_flight);
        tokio::time::sleep(Duration::from_millis(200)).await;
    }

    println!("[GRACEFUL SHUTDOWN] Step 4/4: 释放资源");
    println!("[GRACEFUL SHUTDOWN] ✅ Shutdown complete");
    println!("========================================");
}
