//! 场景 13：CPU 密集并行计算 — Rust 实现（axum + std::thread）
//!
//! 统一 API 契约：
//!     POST /compute
//!     {"task_count":8,"iterations":2000000,"concurrency":4}
//!     → {"total_tasks":8,"iterations":2000000,"concurrency":4,"cpu_cores":10,
//!        "total_time_ms":1234,"checksum":"<uint64 无符号十进制>",
//!        "results":[{"id":0,"checksum":"<uint64>","duration_ms":150}, ...]}
//!
//! Rust 在本场景的三点优势：
//!
//! 1. **真并行 + 无 GC**：`std::thread` 直接映射到 OS 线程，且没有 GC 线程来抢 CPU、
//!    没有 GC 暂停来污染尾延迟 —— 这是"CPU 密集 + 低延迟"场景选 Rust 的核心理由。
//!
//! 2. **`u64` 语义与硬件一致**：`wrapping_mul` / `wrapping_add` 显式声明环绕语义，
//!    不需要像 Python 那样手动 `& MASK`，也不像 TS 那样被迫使用 BigInt。
//!    （注意：不加 `wrapping_*` 时 debug 构建会在溢出处 panic，release 才静默环绕 ——
//!    显式写出来才能保证两种构建行为一致。）
//!
//! 3. **零额外依赖即可实现工作窃取式线程池**：一个 `AtomicUsize` 计数器 + 一个 channel
//!    就够了，不需要 rayon / tokio 的任务编排。下面 20 行代码就是一个完整的固定并发池。
//!
//! 与其余四门语言的对照：
//!   - Java：`Executors.newFixedThreadPool` 更啰嗦，但语义等价；
//!   - Go：`channel` 当信号量，最简洁；
//!   - Python：必须换 `ProcessPoolExecutor`（GIL 限制），代价是序列化与进程启动；
//!   - TS：必须 `worker_threads`，且每个 worker 是独立 JS 堆，无法共享对象。

use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;
use std::time::Instant;

use axum::body::Bytes;
use axum::routing::{get, post};
use axum::{Json, Router};
use serde::{Deserialize, Serialize};

/// MMIX 线性同余发生器常数：state = state * MULT + INC (mod 2^64)
const MULT: u64 = 6364136223846793005;
const INC: u64 = 1442695040888963407;

const DEFAULT_TASK_COUNT: u32 = 8;
const DEFAULT_ITERATIONS: u64 = 2_000_000;
const DEFAULT_CONCURRENCY: u32 = 4;

/// 计算请求；字段缺失时走 `Default`
#[derive(Debug, Deserialize)]
#[serde(default)]
struct ComputeRequest {
    task_count: u32,
    iterations: u64,
    concurrency: u32,
}

impl Default for ComputeRequest {
    fn default() -> Self {
        Self {
            task_count: DEFAULT_TASK_COUNT,
            iterations: DEFAULT_ITERATIONS,
            concurrency: DEFAULT_CONCURRENCY,
        }
    }
}

/// 单任务结果（checksum 必须与其余四门语言逐位一致）
#[derive(Debug, Serialize)]
struct TaskResult {
    id: u32,
    checksum: String,
    duration_ms: u64,
}

/// 计算响应
#[derive(Debug, Serialize)]
struct ComputeResponse {
    total_tasks: u32,
    iterations: u64,
    concurrency: u32,
    cpu_cores: usize,
    total_time_ms: u64,
    checksum: String,
    results: Vec<TaskResult>,
}

/// 跑 `iterations` 次 LCG 迭代，返回 u64 环绕结果
fn compute_state(id: u32, iterations: u64) -> u64 {
    let mut state = id as u64 + 1;
    for _ in 0..iterations {
        state = state.wrapping_mul(MULT).wrapping_add(INC);
    }
    state
}

/// 用「原子计数器 + channel」实现固定并发的工作池（零额外依赖）
fn run(req: ComputeRequest) -> ComputeResponse {
    let task_count = req.task_count.max(1);
    let iterations = req.iterations.max(1);
    let concurrency = req.concurrency.max(1).min(task_count);

    let start = Instant::now();

    let counter = Arc::new(AtomicUsize::new(0));
    let (tx, rx) = std::sync::mpsc::channel::<(u32, u64, u64)>();

    let mut handles = Vec::with_capacity(concurrency as usize);
    for _ in 0..concurrency {
        let counter = Arc::clone(&counter);
        let tx = tx.clone();
        handles.push(std::thread::spawn(move || {
            // 每个线程不断抢下一个任务编号，抢完即退出 —— 天然的负载均衡
            loop {
                let id = counter.fetch_add(1, Ordering::Relaxed) as u32;
                if id >= task_count {
                    break;
                }
                let t0 = Instant::now();
                let state = compute_state(id, iterations);
                let duration_ms = t0.elapsed().as_millis() as u64;
                if tx.send((id, state, duration_ms)).is_err() {
                    break;
                }
            }
        }));
    }
    // 必须丢掉主线程持有的发送端，否则下面的 rx.iter() 永远不会结束
    drop(tx);

    let mut collected: Vec<(u32, u64, u64)> = rx.iter().collect();
    for h in handles {
        let _ = h.join();
    }

    // 结果按 id 升序，保证跨语言可比
    collected.sort_by_key(|r| r.0);

    // 累加和取 u64 环绕（加法模 2^64 满足交换律，与执行顺序无关）
    let checksum = collected
        .iter()
        .fold(0u64, |acc, r| acc.wrapping_add(r.1));

    let results = collected
        .into_iter()
        .map(|(id, state, duration_ms)| TaskResult {
            id,
            checksum: state.to_string(),
            duration_ms,
        })
        .collect();

    ComputeResponse {
        total_tasks: task_count,
        iterations,
        concurrency,
        cpu_cores: std::thread::available_parallelism()
            .map(|n| n.get())
            .unwrap_or(1),
        total_time_ms: start.elapsed().as_millis() as u64,
        checksum: checksum.to_string(),
        results,
    }
}

/// 手动解析 body（而非用 `Json<T>` 提取器）：
/// 这样空 body 也能按缺省值处理，与 Java/Go/Python 的宽松语义保持一致。
async fn handle_compute(body: Bytes) -> Json<ComputeResponse> {
    let req: ComputeRequest = if body.is_empty() {
        ComputeRequest::default()
    } else {
        serde_json::from_slice(&body).unwrap_or_default()
    };

    // CPU 密集计算必须放到阻塞线程池：直接在当前 async 任务里跑会占死一个 runtime worker
    let resp = tokio::task::spawn_blocking(move || run(req))
        .await
        .expect("compute task panicked");
    Json(resp)
}

async fn handle_health() -> Json<serde_json::Value> {
    Json(serde_json::json!({
        "service": "cpu-bound-parallel-rust",
        "cpu_cores": std::thread::available_parallelism().map(|n| n.get()).unwrap_or(1)
    }))
}

#[tokio::main]
async fn main() {
    let app = Router::new()
        .route("/compute", post(handle_compute))
        .route("/health", get(handle_health));

    let addr: std::net::SocketAddr = "0.0.0.0:8138".parse().expect("invalid address");
    println!("[Rust] cpu-bound-parallel server starting on {}", addr);

    let listener = tokio::net::TcpListener::bind(addr)
        .await
        .expect("failed to bind address");
    axum::serve(listener, app).await.expect("server error");
}
