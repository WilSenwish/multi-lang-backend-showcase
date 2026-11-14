//! 场景 17：错误处理深水区 —— Rust 版本。
//!
//! 语义契约（五门语言必须逐字一致，见场景 README）：
//!   `GET /errors/{kind}` —— 五种"错误形态"，每一种都必须落成同一个结构化响应体：
//!     - `not_found`      → 404 NOT_FOUND          cause_chain = ["user 42 not found"]
//!     - `validation`     → 400 VALIDATION_FAILED  details = ["email: required", "age: must be >= 0"]
//!     - `wrap_chain`     → 500 WRAPPED            cause_chain 四层，最外层 → 根因
//!     - `panic`          → 500 INTERNAL           未捕获异常被兜底，recovered=true，进程必须存活
//!     - `async_detached` → 202 ACCEPTED           错误发生在脱离请求上下文的 task 里
//!   `GET /stats` → handled / unhandled / panics_recovered / last_unhandled / last_trace_id
//!   请求头 `X-Trace-Id` 必须原样回显。
//!
//! Rust 的取舍：
//!   - `Result<T, E>` 让"错误必须被处理"成为编译期要求（`?` 只能用于实现了 `Error` 的类型），
//!     但代价是**错误类型必须在签名里出现**：跨层包装要么统一成 `anyhow::Error`（丢掉静态类型），
//!     要么自己写一个枚举把每一层都列出来（样板多，但调用方能 match）。
//!   - `anyhow` 的 `context()` 链只在 `RUST_BACKTRACE=1` 时才捕获 backtrace —— 默认关闭，
//!     这是零成本抽象，但也意味着**默认拿不到栈**。
//!   - panic 在 Rust 里不是错误处理的常规手段：这里用 `catch_unwind` 把它挡在 handler 边界
//!     （`tower_http::CatchPanicLayer` 内部也是同一个机制）。
//!   - ⭐ 深水区：`tokio::spawn` 返回的 `JoinHandle` **被 drop 时，任务里的错误就静默消失** ——
//!     编译器不提醒、运行时不告警。想观测就必须再 spawn 一个"看护"任务去 await 它。

use std::any::Any;
use std::panic::{self, AssertUnwindSafe};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Mutex;
use std::time::Duration;

use anyhow::{anyhow, Context};
use axum::extract::Path;
use axum::http::HeaderMap;
use axum::routing::get;
use axum::{Json, Router};
use serde::Serialize;

const PORT: u16 = 8158;

// ---------------------------------------------------------------- 响应体

#[derive(Serialize)]
struct ErrorBody {
    kind: String,
    code: String,
    message: String,
    trace_id: String,
    cause_chain: Vec<String>,
    details: Vec<String>,
    stack_present: bool,
    recovered: bool,
}

#[derive(Serialize)]
struct StatsBody {
    handled: usize,
    unhandled: usize,
    panics_recovered: usize,
    last_unhandled: String,
    last_trace_id: String,
}

// ---------------------------------------------------------------- 计数器

static HANDLED: AtomicUsize = AtomicUsize::new(0);
static UNHANDLED: AtomicUsize = AtomicUsize::new(0);
static PANICS: AtomicUsize = AtomicUsize::new(0);
static LAST_UNHANDLED: Mutex<String> = Mutex::new(String::new());
static LAST_TRACE: Mutex<String> = Mutex::new(String::new());
static TID_SEQ: AtomicUsize = AtomicUsize::new(0);

fn set_last_trace(id: &str) {
    *LAST_TRACE.lock().unwrap() = id.to_string();
}

fn record_unhandled(msg: String) {
    UNHANDLED.fetch_add(1, Ordering::SeqCst);
    *LAST_UNHANDLED.lock().unwrap() = msg;
}

fn snapshot() -> StatsBody {
    StatsBody {
        handled: HANDLED.load(Ordering::SeqCst),
        unhandled: UNHANDLED.load(Ordering::SeqCst),
        panics_recovered: PANICS.load(Ordering::SeqCst),
        last_unhandled: LAST_UNHANDLED.lock().unwrap().clone(),
        last_trace_id: LAST_TRACE.lock().unwrap().clone(),
    }
}

// ---------------------------------------------------------------- 错误链

/// 四层上下文：db → repository → service → handler。
/// `context()` 把新上下文包在最外层，所以 `chain()` 的迭代顺序天然是"最外层 → 根因"。
fn build_chain() -> anyhow::Error {
    anyhow!("db: row 42 not found")
        .context("repository: load user")
        .context("service: get profile")
        .context("handler: GET /errors/wrap_chain")
}

fn chain_of(err: &anyhow::Error) -> Vec<String> {
    err.chain().map(|e| e.to_string()).collect()
}

/// panic 的 payload 可能是 `&str` 也可能是 `String`，两种都要处理。
fn downcast_panic(v: &(dyn Any + Send)) -> String {
    if let Some(s) = v.downcast_ref::<&str>() {
        (*s).to_string()
    } else if let Some(s) = v.downcast_ref::<String>() {
        s.clone()
    } else {
        "panic".to_string()
    }
}

/// 脱离请求上下文的异步工作：它返回一个普通的 `anyhow::Result`。
/// 关键在调用方 —— `JoinHandle` 被 drop 时这个 Err 就彻底消失了。
async fn detached_work() -> anyhow::Result<()> {
    tokio::time::sleep(Duration::from_millis(120)).await;
    Err(anyhow!("async-boom-17"))
}

// ---------------------------------------------------------------- handler

fn trace_of(headers: &HeaderMap) -> String {
    match headers.get("x-trace-id").and_then(|v| v.to_str().ok()) {
        Some(s) if !s.is_empty() => s.to_string(),
        _ => format!("tid-{}", TID_SEQ.fetch_add(1, Ordering::SeqCst) + 1),
    }
}

async fn handle_errors(
    Path(kind): Path<String>,
    headers: HeaderMap,
) -> (axum::http::StatusCode, Json<ErrorBody>) {
    use axum::http::StatusCode;

    let trace_id = trace_of(&headers);
    set_last_trace(&trace_id);

    macro_rules! body {
        ($status:expr, $code:expr, $msg:expr, $chain:expr, $details:expr, $stack:expr, $recovered:expr) => {
            (
                $status,
                Json(ErrorBody {
                    kind: kind.clone(),
                    code: $code.to_string(),
                    message: $msg,
                    trace_id: trace_id.clone(),
                    cause_chain: $chain,
                    details: $details,
                    stack_present: $stack,
                    recovered: $recovered,
                }),
            )
        };
    }

    match kind.as_str() {
        "not_found" => {
            HANDLED.fetch_add(1, Ordering::SeqCst);
            let err = anyhow!("user 42 not found");
            body!(
                StatusCode::NOT_FOUND,
                "NOT_FOUND",
                err.to_string(),
                chain_of(&err),
                vec![],
                false,
                false
            )
        }

        "validation" => {
            HANDLED.fetch_add(1, Ordering::SeqCst);
            let err = anyhow!("invalid request");
            body!(
                StatusCode::BAD_REQUEST,
                "VALIDATION_FAILED",
                err.to_string(),
                chain_of(&err),
                vec!["email: required".to_string(), "age: must be >= 0".to_string()],
                false,
                false
            )
        }

        "wrap_chain" => {
            HANDLED.fetch_add(1, Ordering::SeqCst);
            let err = build_chain();
            let chain = chain_of(&err);
            let msg = chain.first().cloned().unwrap_or_default();
            body!(
                StatusCode::INTERNAL_SERVER_ERROR,
                "WRAPPED",
                msg,
                chain,
                vec![],
                false,
                false
            )
        }

        "panic" => {
            // panic 在 Rust 里不是错误处理的常规手段：这里在 handler 边界用 catch_unwind 接住
            // （tower_http::CatchPanicLayer 内部也是这个机制），保证进程存活并给出结构化响应。
            // anyhow 的 stack_present 取决于 RUST_BACKTRACE，默认关闭 → 恒为 false。
            let result = panic::catch_unwind(AssertUnwindSafe(|| -> String {
                panic!("boom-17")
            }));
            let msg = match result {
                Err(payload) => downcast_panic(payload.as_ref()),
                Ok(_) => "did not panic".to_string(),
            };
            HANDLED.fetch_add(1, Ordering::SeqCst);
            PANICS.fetch_add(1, Ordering::SeqCst);
            body!(
                StatusCode::INTERNAL_SERVER_ERROR,
                "INTERNAL",
                msg.clone(),
                vec![msg],
                vec![],
                false,
                true
            )
        }

        "async_detached" => {
            // ⭐ 深水区：handle 一旦被 drop，detached_work 返回的 Err 就**静默消失**。
            // 所以这里再 spawn 一个"看护"任务专门 await 它 —— 这段是手写的，Rust 不会替你做。
            let handle = tokio::spawn(detached_work());
            tokio::spawn(async move {
                match handle.await {
                    Ok(Ok(())) => {}
                    Ok(Err(e)) => record_unhandled(e.to_string()),
                    Err(join_err) => record_unhandled(format!("{}", join_err)),
                }
            });
            body!(
                StatusCode::ACCEPTED,
                "ACCEPTED",
                "async work spawned".to_string(),
                vec![],
                vec![],
                false,
                false
            )
        }

        other => {
            let msg = format!("unknown kind: {}", other);
            body!(
                StatusCode::NOT_FOUND,
                "UNKNOWN_KIND",
                msg.clone(),
                vec![msg],
                vec![],
                false,
                false
            )
        }
    }
}

async fn handle_stats() -> Json<StatsBody> {
    Json(snapshot())
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
        .route("/errors/:kind", get(handle_errors))
        .route("/stats", get(handle_stats));

    let addr = format!("127.0.0.1:{}", PORT);
    tracing::info!(addr = %addr, "server starting");
    let listener = tokio::net::TcpListener::bind(&addr).await.unwrap();
    axum::serve(listener, app).await.unwrap();
}
