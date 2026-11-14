//! 场景 15：结构化并发 + 取消传播 —— Rust 用 tokio `JoinSet` + `watch` 广播取消。
//!
//! 语义契约（五门语言必须逐字一致，见场景 README）：
//!   - 扇出 tasks 个子任务，id = 0..tasks-1，全部并发启动
//!   - id == fail_index 的子任务在 fail_after_ms 后"失败"；其余子任务跑满 task_ms 后"完成"
//!   - 任一子任务失败 / 父作用域超时 → 取消信号必须广播到所有兄弟任务（cancelled）
//!   - 作用域退出时所有子任务必须已结束（结构化保证），leaked 恒为 0
//!
//! Rust 的取舍：**没有语言级结构化并发**（截至 2026 年仍未稳定），取消传播要自己搭：
//! 这里用 `watch::channel` 做"取消广播"，`JoinSet` 负责结构化收尾（drop 即 abort）。
//! 好处是取消语义显式可见（每个 await 点都必须 select 取消信号），代价是每个等待点都要写。

use std::sync::atomic::{AtomicI64, Ordering};
use std::time::Duration;

use axum::routing::{get, post};
use axum::{Json, Router};
use serde::{Deserialize, Serialize};
use tokio::sync::watch;
use tokio::task::JoinSet;
use tokio::time::Instant;

const PORT: u16 = 8148;

// ---- 运行时统计（供 /stats 暴露，验证器用它做"取消是否真的生效"的延迟判定）----
static ACTIVE: AtomicI64 = AtomicI64::new(0);
static STARTED: AtomicI64 = AtomicI64::new(0);
static DONE: AtomicI64 = AtomicI64::new(0);
static CANCELLED: AtomicI64 = AtomicI64::new(0);
static FAILED: AtomicI64 = AtomicI64::new(0);

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Outcome {
    Completed,
    Cancelled,
    Failed,
}

impl Outcome {
    fn as_str(&self) -> &'static str {
        match self {
            Outcome::Completed => "completed",
            Outcome::Cancelled => "cancelled",
            Outcome::Failed => "failed",
        }
    }
}

#[derive(Deserialize)]
struct FanoutRequest {
    #[serde(default)]
    tasks: Option<usize>,
    #[serde(default)]
    task_ms: Option<u64>,
    #[serde(default)]
    fail_index: Option<i64>,
    #[serde(default)]
    fail_after_ms: Option<u64>,
    #[serde(default)]
    timeout_ms: Option<u64>,
}

#[derive(Serialize)]
struct FanoutResponse {
    lang: &'static str,
    tasks: usize,
    task_ms: u64,
    fail_index: i64,
    fail_after_ms: u64,
    timeout_ms: u64,
    outcome: String, // completed | failed | timeout
    completed: Vec<usize>,
    cancelled: Vec<usize>,
    failed: i64,
    elapsed_ms: i64,
    leaked: i64,
}

#[derive(Serialize)]
struct StatsResponse {
    lang: &'static str,
    active_tasks: i64,
    started: i64,
    completed: i64,
    cancelled: i64,
    failed: i64,
}

fn bad_request(msg: &str) -> (axum::http::StatusCode, Json<serde_json::Value>) {
    (
        axum::http::StatusCode::BAD_REQUEST,
        Json(serde_json::json!({ "error": msg })),
    )
}

async fn health() -> Json<serde_json::Value> {
    Json(serde_json::json!({
        "service": "structured-concurrency", "lang": "rust", "engine": "tokio JoinSet + watch",
    }))
}

async fn stats() -> Json<StatsResponse> {
    Json(StatsResponse {
        lang: "rust",
        active_tasks: ACTIVE.load(Ordering::SeqCst),
        started: STARTED.load(Ordering::SeqCst),
        completed: DONE.load(Ordering::SeqCst),
        cancelled: CANCELLED.load(Ordering::SeqCst),
        failed: FAILED.load(Ordering::SeqCst),
    })
}

/// 可中断的等待：要么等满 `ms`，要么被取消信号唤醒。
/// **每个等待点都必须这样写** —— 这是 Rust 侧"取消传播"的全部实现成本。
async fn wait_or_cancel(ms: u64, cancel: &mut watch::Receiver<bool>) -> Result<(), ()> {
    if *cancel.borrow_and_update() {
        return Err(());
    }
    let sleep = tokio::time::sleep(Duration::from_millis(ms));
    tokio::pin!(sleep);
    tokio::select! {
        _ = &mut sleep => Ok(()),
        _ = cancel.changed() => Err(()),
    }
}

async fn run_task(
    id: usize,
    task_ms: u64,
    fail_index: i64,
    fail_after_ms: u64,
    mut cancel: watch::Receiver<bool>,
) -> (usize, Outcome) {
    STARTED.fetch_add(1, Ordering::SeqCst);
    ACTIVE.fetch_add(1, Ordering::SeqCst);

    let outcome = if id as i64 == fail_index {
        match wait_or_cancel(fail_after_ms, &mut cancel).await {
            Ok(()) => {
                FAILED.fetch_add(1, Ordering::SeqCst);
                Outcome::Failed
            }
            Err(()) => Outcome::Cancelled, // 还没来得及失败就被取消（超时抢占）
        }
    } else {
        match wait_or_cancel(task_ms, &mut cancel).await {
            Ok(()) => {
                DONE.fetch_add(1, Ordering::SeqCst);
                Outcome::Completed
            }
            Err(()) => {
                CANCELLED.fetch_add(1, Ordering::SeqCst);
                Outcome::Cancelled
            }
        }
    };

    ACTIVE.fetch_sub(1, Ordering::SeqCst);
    (id, outcome)
}

async fn fanout(
    Json(req): Json<FanoutRequest>,
) -> Result<Json<FanoutResponse>, (axum::http::StatusCode, Json<serde_json::Value>)> {
    let tasks = req.tasks.unwrap_or(6);
    let task_ms = req.task_ms.unwrap_or(300);
    let fail_index = req.fail_index.unwrap_or(-1);
    let fail_after_ms = req.fail_after_ms.unwrap_or(100);
    let timeout_ms = req.timeout_ms.unwrap_or(0);

    if tasks < 1 || tasks > 64 {
        return Err(bad_request("tasks must be in [1, 64]"));
    }
    if task_ms < 1 || task_ms > 10_000 {
        return Err(bad_request("task_ms must be in [1, 10000]"));
    }
    if fail_index < -1 || fail_index >= tasks as i64 {
        return Err(bad_request("fail_index must be in [-1, tasks)"));
    }
    if fail_after_ms > 10_000 {
        return Err(bad_request("fail_after_ms must be in [0, 10000]"));
    }
    if timeout_ms > 10_000 {
        return Err(bad_request("timeout_ms must be in [0, 10000]"));
    }

    let t0 = Instant::now();

    // 取消广播通道：值变为 true 即"作用域已取消"，所有子任务的 changed() 会立即返回
    let (cancel_tx, _) = watch::channel(false);
    let mut set: JoinSet<(usize, Outcome)> = JoinSet::new();
    for i in 0..tasks {
        let rx = cancel_tx.subscribe();
        set.spawn(run_task(i, task_ms, fail_index, fail_after_ms, rx));
    }

    let deadline = if timeout_ms > 0 {
        Some(t0 + Duration::from_millis(timeout_ms))
    } else {
        None
    };

    // 按 id 存结果（join_next 的返回顺序是"完成顺序"，不能直接按下标 push）
    let mut outcomes: Vec<Option<Outcome>> = vec![None; tasks];
    let mut finished = vec![false; tasks];
    let mut collected = 0usize;
    let mut timed_out = false;

    while collected < tasks {
        let next = match deadline {
            Some(dl) => match tokio::time::timeout_at(dl, set.join_next()).await {
                Ok(res) => res,
                Err(_) => {
                    // 超时：广播取消后继续收尾（子任务会立刻以 Cancelled 退出）
                    timed_out = true;
                    let _ = cancel_tx.send(true);
                    set.join_next().await
                }
            },
            None => set.join_next().await,
        };
        match next {
            Some(Ok((id, outcome))) => {
                if outcome == Outcome::Failed {
                    // 失败即广播取消（fail-fast 的取消传播）
                    let _ = cancel_tx.send(true);
                }
                outcomes[id] = Some(outcome);
                finished[id] = true;
                collected += 1;
            }
            Some(Err(e)) => {
                // 任务 panic / 被 abort：仍要把它算作已收尾，避免死循环
                tracing::error!(error = ?e, "task error");
                collected += 1;
            }
            None => break,
        }
    }

    // 兜底：若仍有任务未回报（例如 JoinSet 被 abort），补为 cancelled，保证契约字段完整
    let mut completed = Vec::new();
    let mut cancelled = Vec::new();
    let mut failed = -1i64;
    for (i, done) in finished.iter().enumerate() {
        let o = outcomes[i].unwrap_or(Outcome::Cancelled);
        match o {
            Outcome::Completed => completed.push(i),
            Outcome::Cancelled => cancelled.push(i),
            Outcome::Failed => failed = i as i64,
        }
    }
    completed.sort_unstable();
    cancelled.sort_unstable();

    let outcome = if failed >= 0 {
        "failed"
    } else if !cancelled.is_empty() {
        "timeout"
    } else if timed_out {
        "timeout"
    } else {
        "completed"
    };

    Ok(Json(FanoutResponse {
        lang: "rust",
        tasks,
        task_ms,
        fail_index,
        fail_after_ms,
        timeout_ms,
        outcome: outcome.to_string(),
        completed,
        cancelled,
        failed,
        elapsed_ms: t0.elapsed().as_millis() as i64,
        leaked: ACTIVE.load(Ordering::SeqCst),
    }))
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
        .route("/health", get(health))
        .route("/stats", get(stats))
        .route("/fanout", post(fanout));

    let addr = format!("0.0.0.0:{}", PORT);
    tracing::info!(addr = %addr, "server starting");
    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    axum::serve(listener, app).await.unwrap();
}
