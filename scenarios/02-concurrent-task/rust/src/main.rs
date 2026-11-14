//! 场景 02：并发任务处理 — Rust 实现 (axum + tokio)
//!
//! Rust 并发模型特点：
//! 1. tokio 是多线程异步运行时（和 Python asyncio 的单线程不同）
//! 2. tokio::Semaphore 是并发限流原语
//! 3. JoinHandle 是 spawn 后返回的句柄，.await 等待完成
//! 4. **编译期保证无数据竞争**（所有权 + Send/Sync trait）
//! 5. 没有 GC 暂停，性能可与 C/C++ 媲美
//!
//! 和其他语言的本质区别：
//! - Java/Go/Rust 都是真多线程
//! - 但 Rust 编译器帮你检查线程安全，不会有数据竞争
//! - Python asyncio / TS 事件循环是单线程伪并行

use axum::{
    body::Bytes,
    extract::State,
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::post,
    Json, Router,
};
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tokio::sync::Semaphore;
use tokio::time::{sleep, Duration};

#[derive(Deserialize)]
struct RunRequest {
    #[serde(default = "default_task_count")]
    task_count: i64,
    #[serde(default = "default_task_delay_ms")]
    task_delay_ms: i64,
    #[serde(default = "default_concurrency")]
    concurrency: i64,
}

fn default_task_count() -> i64 {
    100
}
fn default_task_delay_ms() -> i64 {
    100
}
fn default_concurrency() -> i64 {
    10
}

#[derive(Serialize, Clone)]
struct TaskResult {
    id: i64,
    status: &'static str,
    duration_ms: u128,
}

#[derive(Serialize)]
struct RunResponse {
    total_tasks: i64,
    concurrency: i64,
    total_time_ms: u128,
    throughput: f64,
    task_delay_ms: i64,
    results: Vec<TaskResult>,
}

/// 应用状态（持有共享的 tokio 运行时）
#[derive(Clone)]
struct AppState;

/// 400 响应（统一契约：畸形 JSON / 类型错误 / 非法值都走这里）
fn bad_request(msg: &str) -> Response {
    (StatusCode::BAD_REQUEST, msg.to_string()).into_response()
}

async fn run(State(_): State<AppState>, body: Bytes) -> Response {
    // 手动解析而非 axum 的 Json 提取器：后者对"语法错误"给 400、对"类型错误"给 422，
    // 与其余四门语言不一致；这里统一映射为 400（契约：非法入参一律 400）。
    let req: RunRequest = match serde_json::from_slice(&body) {
        Ok(r) => r,
        Err(e) => return bad_request(&format!("invalid request body: {e}")),
    };

    // 边界保护 → 契约：显式非法值一律 400，不再静默夹取
    if req.task_count < 1 {
        return bad_request("task_count must be >= 1");
    }
    if req.task_delay_ms < 0 {
        return bad_request("task_delay_ms must be >= 0");
    }
    if req.concurrency < 1 {
        return bad_request("concurrency must be >= 1");
    }

    let task_count = req.task_count;
    let delay_ms = req.task_delay_ms;
    // 并发数不超过任务数（契约行为）
    let concurrency = req.concurrency.min(task_count);

    let start = std::time::Instant::now();

    // ========== Rust tokio 并发核心 ==========
    // Arc<Semaphore> 需要 clone 给每个 spawn 任务
    let semaphore = Arc::new(Semaphore::new(concurrency as usize));

    let mut handles = Vec::with_capacity(task_count as usize);

    for id in 0..task_count {
        let sem_clone = Arc::clone(&semaphore);
        handles.push(tokio::spawn(async move {
            // acquire_owned 获得许可（和 Java ThreadPool / Go channel / Python Semaphore 同义）
            let _permit = sem_clone.acquire_owned().await.unwrap();

            let task_start = std::time::Instant::now();
            sleep(Duration::from_millis(delay_ms as u64)).await;
            let duration_ms = task_start.elapsed().as_millis();

            // _permit 离开作用域自动释放 — Rust 的 RAII
            TaskResult {
                id,
                status: "ok",
                duration_ms,
            }
        }));
    }

    // 等待所有 spawn 完成（.await 会传播错误）
    let mut results = Vec::with_capacity(task_count as usize);
    for h in handles {
        results.push(h.await.unwrap());
    }
    // =========================================

    let total_ms = start.elapsed().as_millis();
    let throughput = if total_ms > 0 {
        (task_count as f64) * 1000.0 / (total_ms as f64)
    } else {
        task_count as f64
    };

    Json(RunResponse {
        total_tasks: task_count,
        concurrency,
        total_time_ms: total_ms,
        throughput: (throughput * 100.0).round() / 100.0,
        task_delay_ms: delay_ms,
        results,
    })
    .into_response()
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

    let app = Router::new()
        .route("/run", post(run))
        .with_state(AppState);

    let addr = "0.0.0.0:8088";
    tracing::info!(addr = %addr, "server starting");

    let listener = tokio::net::TcpListener::bind(addr)
        .await
        .expect("failed to bind address");
    axum::serve(listener, app).await.expect("server error");
}
