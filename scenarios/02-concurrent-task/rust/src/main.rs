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
    extract::State,
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
    task_count: u32,
    #[serde(default)]
    task_delay_ms: u64,
    #[serde(default = "default_concurrency")]
    concurrency: u32,
}

fn default_task_count() -> u32 {
    100
}
fn default_concurrency() -> u32 {
    10
}

#[derive(Serialize, Clone)]
struct TaskResult {
    id: u32,
    status: &'static str,
    duration_ms: u128,
}

#[derive(Serialize)]
struct RunResponse {
    total_tasks: u32,
    concurrency: u32,
    total_time_ms: u128,
    throughput: f64,
    task_delay_ms: u64,
    results: Vec<TaskResult>,
}

/// 应用状态（持有共享的 tokio 运行时）
#[derive(Clone)]
struct AppState;

async fn run(
    State(_): State<AppState>,
    Json(req): Json<RunRequest>,
) -> Json<RunResponse> {
    // 边界保护
    let task_count = req.task_count.max(1);
    let delay_ms = req.task_delay_ms;
    let concurrency = req.concurrency.max(1).min(task_count);

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
            sleep(Duration::from_millis(delay_ms)).await;
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
}

#[tokio::main]
async fn main() {
    let app = Router::new()
        .route("/run", post(run))
        .with_state(AppState);

    let addr = "0.0.0.0:8088";
    println!("[Rust] concurrent-task server starting on {}", addr);

    let listener = tokio::net::TcpListener::bind(addr)
        .await
        .expect("failed to bind address");
    axum::serve(listener, app).await.expect("server error");
}
