//! 场景 10：单机内存限流 — Rust 实现（axum + 手写令牌桶）
//!
//! Rust 限流特点：
//! 1. governor = Rust 生态限流事实标准（支持多种算法）
//! 2. 这里手写实现，展示 Rust 的原子操作 + 锁性能
//! 3. Mutex 保证并发安全（Rust 编译器强制检查）
//! 4. governor 也可以用，但手写更直观
//!
//! 并发安全：Mutex<State> 保证线程安全，编译器强制检查，
//! 不可能写出数据竞争（Rust 的核心优势！）

use axum::{
    extract::State,
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::{get},
    Router,
};
use serde::{Deserialize, Serialize};
use std::sync::{Arc, Mutex};
use std::time::Instant;

// ==================== 令牌桶 ====================

struct TokenBucket {
    qps: f64,
    burst: u64,
    tokens: f64,
    last_refill: Instant,
    total: u64,
    allowed: u64,
    rejected: u64,
}

impl TokenBucket {
    fn new(qps: f64, burst: u64) -> Self {
        Self {
            qps,
            burst,
            tokens: burst as f64,
            last_refill: Instant::now(),
            total: 0,
            allowed: 0,
            rejected: 0,
        }
    }

    fn refill(&mut self) {
        let elapsed = self.last_refill.elapsed().as_secs_f64();
        let refill = elapsed * self.qps;
        self.tokens = (self.burst as f64).min(self.tokens + refill);
        self.last_refill = Instant::now();
    }

    fn try_acquire(&mut self) -> bool {
        self.refill();
        if self.tokens >= 1.0 {
            self.tokens -= 1.0;
            self.total += 1;
            self.allowed += 1;
            true
        } else {
            self.total += 1;
            self.rejected += 1;
            false
        }
    }

    fn retry_after_ms(&mut self) -> u64 {
        self.refill();
        let deficit = 1.0 - self.tokens;
        if deficit <= 0.0 {
            return 0;
        }
        (deficit / self.qps * 1000.0) as u64
    }
}

type SharedBucket = Arc<Mutex<TokenBucket>>;

// ==================== Handler ====================

async fn heavy_handler(State(bucket): State<SharedBucket>) -> Response {
    let mut b = bucket.lock().unwrap();

    if !b.try_acquire() {
        let retry_ms = b.retry_after_ms();
        let total = b.total;
        let allowed = b.allowed;
        let rejected = b.rejected;
        drop(b);

        let body = serde_json::json!({
            "error": "rate limit exceeded",
            "retry_after_ms": retry_ms,
            "total": total,
            "allowed": allowed,
            "rejected": rejected,
        });

        return (
            StatusCode::TOO_MANY_REQUESTS,
            axum::response::AppendHeaders([(
                axum::http::header::RETRY_AFTER,
                format!("{}", (retry_ms / 1000 + 1).max(1)),
            )]),
            axum::Json(body),
        )
            .into_response();
    }

    let total = b.total;
    let allowed = b.allowed;
    let rejected = b.rejected;

    axum::Json(serde_json::json!({
        "ok": true,
        "endpoint": "/api/heavy",
        "total": total,
        "allowed": allowed,
        "rejected": rejected,
    }))
    .into_response()
}

async fn health_handler(State(bucket): State<SharedBucket>) -> Response {
    let b = bucket.lock().unwrap();
    axum::Json(serde_json::json!({
        "service": "rate-limit-rust",
        "algorithm": "token-bucket (Mutex<TokenBucket>)",
        "qps": b.qps,
        "burst": b.burst,
        "total": b.total,
        "allowed": b.allowed,
        "rejected": b.rejected,
    }))
    .into_response()
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

    tracing::debug!("rate limit config: QPS=1, burst=10 (1 token per second, bucket capacity 10)");
    tracing::debug!("Rust Mutex ensures concurrency safety, compiler enforces data race check");

    let bucket = Arc::new(Mutex::new(TokenBucket::new(1.0, 10)));
    let app = Router::new()
        .route("/api/heavy", get(heavy_handler))
        .route("/health", get(health_handler))
        .with_state(bucket);

    let listener = tokio::net::TcpListener::bind("0.0.0.0:8123").await.unwrap();
    tracing::info!(addr = "0.0.0.0:8123", "server starting");
    axum::serve(listener, app).await.unwrap();
}
