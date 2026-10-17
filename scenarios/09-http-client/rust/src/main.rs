//! 场景 09：HTTP 客户端（超时 / 重试 / 熔断） — Rust 实现
//!
//! Rust HTTP Client 特点：
//! 1. reqwest = Rust 生态事实标准（基于 tokio，原生 async）
//! 2. reqwest.Client 默认连接池，max_connections 配置
//! 3. 超时：connect_timeout + request timeout 分开配置
//! 4. 重试：手动指数退避（backoff crate 可选）
//! 5. 熔断：手动实现（简单够用）
//!
//! 和其他语言对比：
//! - reqwest 是 async-first 设计，没有同步 API 历史包袱
//! - Rust 的 Result 让错误处理编译器强制

use axum::{
    extract::State,
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::{get, post},
    Router,
};
use reqwest::Method;
use serde::{Deserialize, Serialize};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use tokio::time::sleep;

const MOCK_PORT: u16 = 8203;

// ==================== Mock Server ====================

async fn mock_router() -> Router {
    Router::new()
        .route("/ok", get(|| async {
            axum::Json(serde_json::json!({"ok": true, "service": "rust-mock"}))
        }))
        .route("/slow", get(|| async {
            tokio::time::sleep(Duration::from_secs(2)).await;
            axum::Json(serde_json::json!({"ok": true, "slow": true}))
        }))
        .route("/fail", get(|| async {
            (StatusCode::INTERNAL_SERVER_ERROR, axum::Json(serde_json::json!({"error": "mock failure"})))
        }))
}

// ==================== 熔断（手动实现） ====================

#[derive(Debug)]
struct CircuitBreaker {
    failure_count: Mutex<u32>,
    threshold: u32,
    half_open_after: Duration,
    last_failure: Mutex<Option<Instant>>,
    state: Mutex<String>, // "closed" / "open" / "half-open"
}

impl CircuitBreaker {
    fn new(threshold: u32, half_open_after: Duration) -> Self {
        Self {
            failure_count: Mutex::new(0),
            threshold,
            half_open_after,
            last_failure: Mutex::new(None),
            state: Mutex::new("closed".into()),
        }
    }

    fn allow(&self) -> bool {
        let mut state = self.state.lock().unwrap();
        match state.as_str() {
            "closed" => true,
            "open" => {
                let last = self.last_failure.lock().unwrap();
                if last.is_some_and(|t| t.elapsed() >= self.half_open_after) {
                    *state = "half-open".into();
                    true
                } else {
                    false
                }
            }
            _ => true,
        }
    }

    fn record_success(&self) {
        *self.failure_count.lock().unwrap() = 0;
        *self.state.lock().unwrap() = "closed".into();
    }

    fn record_failure(&self) {
        let mut fc = self.failure_count.lock().unwrap();
        *fc += 1;
        let mut last = self.last_failure.lock().unwrap();
        *last = Some(Instant::now());
        let mut state = self.state.lock().unwrap();
        if *fc >= self.threshold {
            *state = "open".into();
        }
    }

    fn state_str(&self) -> String {
        self.state.lock().unwrap().clone()
    }
}

// ==================== 请求/响应模型 ====================

fn default_url() -> String {
    format!("http://localhost:{MOCK_PORT}/ok")
}
fn default_timeout_ms() -> u64 {
    5000
}
fn default_retry_times() -> u32 {
    2 // 总尝试次数 = retry_times + 1
}

#[derive(Deserialize)]
struct CallReq {
    // serde(default)：缺字段时用默认值。不用 Option 是因为 axum::Json 对缺字段
    // 直接 422，而其他四门语言都接受"只传部分字段"的请求体（README 统一接口）。
    #[serde(default = "default_url")]
    url: String,
    #[serde(default = "default_timeout_ms")]
    timeout_ms: u64,
    #[serde(default = "default_retry_times")]
    retry_times: u32,
}

// 响应键集合分三种形态（跨语言统一契约，与 Go/Python/TS/Java 逐字段一致）：
//   成功      {status_code, latency_ms, retries, success, body_preview, url, timestamp}
//   重试耗尽  {status_code, latency_ms, retries, success, error, url, timestamp}
//   熔断中    {status_code:0, latency_ms:0, retries:0, success:false, error:"CIRCUIT_OPEN: 熔断中", url, timestamp}
// Option 字段必须 skip_serializing_if：否则成功响应会多个 error:null、
// 失败响应会多个 body_preview:null，键集合与其他语言对不上。
#[derive(Serialize, Default)]
struct CallResp {
    success: bool,
    status_code: u16,
    latency_ms: u128,
    retries: u32,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    body_preview: Option<serde_json::Value>,
    url: String,
    timestamp: String,
}

impl CallResp {
    fn new(url: String) -> Self {
        Self {
            url,
            timestamp: chrono::Utc::now().to_rfc3339(),
            ..Default::default()
        }
    }
}

// ==================== HTTP Client 核心 ====================

type AppState = Arc<CircuitBreaker>;

async fn call_handler(
    State(cb): State<AppState>,
    axum::Json(req): axum::Json<CallReq>,
) -> Response {
    let url = if req.url.is_empty() {
        default_url()
    } else {
        req.url.clone()
    };
    let total_timeout = Duration::from_millis(req.timeout_ms);
    let max_attempts = req.retry_times + 1;

    // 熔断检查
    if !cb.allow() {
        let mut resp = CallResp::new(url);
        resp.success = false;
        resp.error = Some("CIRCUIT_OPEN: 熔断中".into());
        return axum::Json(resp).into_response();
    }

    // reqwest 客户端（连接池 + 超时）
    let client = match reqwest::Client::builder()
        .connect_timeout(Duration::from_secs(3))
        .build()
    {
        Ok(c) => c,
        Err(e) => {
            let mut resp = CallResp::new(url);
            resp.success = false;
            resp.error = Some(format!("client build failed: {e}"));
            return axum::Json(resp).into_response();
        }
    };

    let start = Instant::now();
    let mut final_resp: Option<CallResp> = None;
    let mut last_error: Option<String> = None;
    let mut attempts_made = 0u32;

    for attempt in 0..max_attempts {
        attempts_made = attempt + 1;

        // 指数退避（首次不等待）
        if attempt > 0 {
            let backoff_ms: u64 = 100 * (1 << (attempt - 1)); // 100 → 200 → 400
            sleep(Duration::from_millis(backoff_ms)).await;
        }

        println!("[HTTP-CLIENT] → GET {} (attempt {})", url, attempt + 1);

        match client
            .request(Method::GET, &url)
            .timeout(total_timeout)
            .send()
            .await
        {
            Ok(resp) => {
                let code = resp.status().as_u16();

                // 5xx 重试；最后一次也失败时按"重试耗尽"语义返回真实状态码
                // （README 统一接口：重试 2 次后 status_code=500），且必须记熔断失败 ——
                // 老代码在这里落进成功分支，把 500 记成 success，熔断器永远打不开。
                if code >= 500 {
                    last_error = Some(format!("HTTP {code}"));
                    if attempt < max_attempts - 1 {
                        continue;
                    }
                    cb.record_failure();
                    let mut r = CallResp::new(url.clone());
                    r.success = false;
                    r.status_code = code;
                    r.latency_ms = start.elapsed().as_millis();
                    r.retries = attempt;
                    r.error = last_error;
                    return axum::Json(r).into_response();
                }

                let latency = start.elapsed().as_millis();
                let text = resp.text().await.unwrap_or_default();
                let body: Option<serde_json::Value> = serde_json::from_str(&text).ok();

                cb.record_success();

                final_resp = Some(CallResp {
                    success: code < 400,
                    status_code: code,
                    latency_ms: latency,
                    retries: attempt,
                    error: None,
                    body_preview: body,
                    url: url.clone(),
                    timestamp: chrono::Utc::now().to_rfc3339(),
                });
                break;
            }
            Err(e) => {
                last_error = Some(e.to_string());
                // 最后一次尝试也失败
                if attempt >= max_attempts - 1 {
                    break;
                }
            }
        }
    }

    let final_latency = start.elapsed().as_millis();
    match final_resp {
        Some(r) => axum::Json(r).into_response(),
        None => {
            cb.record_failure();
            let mut resp = CallResp::new(url);
            resp.success = false;
            resp.latency_ms = final_latency;
            resp.retries = attempts_made.saturating_sub(1);
            resp.error = Some(last_error.unwrap_or_else(|| "unknown error".into()));
            axum::Json(resp).into_response()
        }
    }
}

async fn health_handler(State(cb): State<AppState>) -> Response {
    axum::Json(serde_json::json!({
        "service": "http-client-rust",
        "mock_port": MOCK_PORT,
        "cb_state": cb.state_str(),
    }))
    .into_response()
}

// ==================== main ====================

#[tokio::main]
async fn main() {
    // 启动 mock server
    let mock = mock_router().await;
    let mock_listener = tokio::net::TcpListener::bind(format!("0.0.0.0:{MOCK_PORT}"))
        .await
        .unwrap();
    // axum 0.7 的 Serve 实现的是 IntoFuture(而非 Future)，不能直接交给 tokio::spawn，
    // 需包进 async 块内 await，否则报 "Serve is not a future"
    tokio::spawn(async move { axum::serve(mock_listener, mock).await });
    println!("[Rust MockServer] starting on http://localhost:{MOCK_PORT}");

    let cb = Arc::new(CircuitBreaker::new(3, Duration::from_secs(10)));
    let app = Router::new()
        .route("/call-external", post(call_handler))
        .route("/health", get(health_handler))
        .with_state(cb.clone());

    let listener = tokio::net::TcpListener::bind("0.0.0.0:8118").await.unwrap();
    println!("[Rust] http-client server starting on 0.0.0.0:8118");
    axum::serve(listener, app).await.unwrap();
}
