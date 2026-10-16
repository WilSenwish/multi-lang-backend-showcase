//! 场景 01：JSON 序列化/反序列化 — Rust 实现 (axum + serde)
//!
//! serde 特点（和 Java Jackson / Go encoding/json 对比）：
//! 1. **编译期**：`#[derive(Serialize, Deserialize)]` 编译时生成代码
//! 2. 零运行时开销（单态化 + 无虚函数）
//! 3. Option<T> → Some(v) 输出值，None 输出 null（或 skip_serializing_if="Option::is_none"）
//! 4. Vec<T> → 空 Vec 输出 []，None 输出 null
//! 5. 字段名默认匹配，#[serde(rename = "name")] 可映射
//! 6. 可选 skip_serializing_if / default / flatten 等属性
//!
//! 关键差异：
//! - Rust 空 Vec → JSON []（和 Java/Go/Python 一致）
//! - Rust Option::None → JSON null（和 Go 指针一致）
//! - serde_json 性能极高（和 Go encoding/json 接近，远快于 Python）

use axum::{
    extract::{State, Json as AxumJson},
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::{get, post},
    Router,
};
use serde::{Deserialize, Serialize};
use std::time::Instant;

// ==================== 数据结构 ====================

#[derive(Serialize, Deserialize, Clone)]
struct Address {
    city: String,
    zip: String,
}

#[derive(Serialize, Deserialize, Clone)]
struct User {
    id: u32,
    name: String,
    /// Option<String> → Some(s) 输出 "s"，None 输出 null
    email: Option<String>,
    age: u32,
    tags: Vec<String>,
    address: Address,
    /// Vec<i32> → 空 Vec 输出 []
    scores: Vec<i32>,
}

impl User {
    fn demo() -> Self {
        User {
            id: 1,
            name: "Alice".into(),
            email: None, // → JSON null
            age: 28,
            tags: vec!["engineer".into(), "java".into()],
            address: Address {
                city: "Beijing".into(),
                zip: "100000".into(),
            },
            scores: vec![], // → JSON []
        }
    }
}

// 用于接受任意 JSON 对象（serialize/deserialize/roundtrip 端点）
type JsonMap = serde_json::Value;

// ==================== 统一响应 ====================

fn ok<T: Serialize>(data: T) -> Response {
    (StatusCode::OK, AxumJson(data)).into_response()
}

// ==================== 5 个 Handler ====================

// GET /demo
async fn demo(State(_): State<()>) -> Response {
    ok(User::demo())
}

// POST /serialize
async fn serialize(State(_): State<()>, AxumJson(body): AxumJson<JsonMap>) -> Response {
    let start = Instant::now();
    let json_str = match serde_json::to_string(&body) {
        Ok(s) => s,
        Err(e) => return (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()).into_response(),
    };
    let elapsed_us = start.elapsed().as_micros();

    let pretty = serde_json::to_string_pretty(&body).unwrap_or_default();

    let resp = serde_json::json!({
        "json": json_str,
        "bytes": json_str.len(),
        "time_us": elapsed_us as u64,
        "pretty": pretty,
    });
    ok(resp)
}

// POST /deserialize
#[derive(Deserialize)]
struct DesReq {
    json_string: String,
}

async fn deserialize(State(_): State<()>, AxumJson(body): AxumJson<DesReq>) -> Response {
    let start = Instant::now();
    let parsed: JsonMap = match serde_json::from_str(&body.json_string) {
        Ok(v) => v,
        Err(e) => return (StatusCode::BAD_REQUEST, e.to_string()).into_response(),
    };
    let elapsed_us = start.elapsed().as_micros();

    let resp = serde_json::json!({
        "parsed": parsed,
        "time_us": elapsed_us as u64,
        "size": body.json_string.len(),
    });
    ok(resp)
}

// POST /roundtrip
async fn roundtrip(State(_): State<()>, AxumJson(body): AxumJson<JsonMap>) -> Response {
    let json1 = serde_json::to_string(&body).unwrap_or_default();
    let parsed: JsonMap = serde_json::from_str(&json1).unwrap_or(serde_json::Value::Null);
    let json2 = serde_json::to_string(&parsed).unwrap_or_default();

    let resp = serde_json::json!({
        "original_json": json1,
        "roundtrip_json": json2,
        "equal": json1 == json2,
        "original_bytes": json1.len(),
        "roundtrip_bytes": json2.len(),
    });
    ok(resp)
}

// GET /bench
async fn bench(State(_): State<()>) -> Response {
    let user = User::demo();
    let iterations: u32 = 10000;

    // 预热
    for _ in 0..100 {
        let s = serde_json::to_string(&user).unwrap();
        let _: JsonMap = serde_json::from_str(&s).unwrap();
    }

    let start = Instant::now();
    let mut last_json = String::new();
    for _ in 0..iterations {
        last_json = serde_json::to_string(&user).unwrap();
        let _: JsonMap = serde_json::from_str(&last_json).unwrap();
    }
    let total_ms = start.elapsed().as_millis();

    let avg_us = (total_ms as f64 * 1000.0) / (iterations as f64);

    let resp = serde_json::json!({
        "language": "rust-serde",
        "iterations": iterations,
        "total_time_ms": total_ms as u64,
        "avg_time_us": (avg_us * 100.0).round() / 100.0,
        "json_size_bytes": last_json.len(),
    });
    ok(resp)
}

// ==================== main ====================

#[tokio::main]
async fn main() {
    let app = Router::new()
        .route("/demo", get(demo))
        .route("/serialize", post(serialize))
        .route("/deserialize", post(deserialize))
        .route("/roundtrip", post(roundtrip))
        .route("/bench", get(bench))
        .with_state(());

    let addr = "0.0.0.0:8093";
    println!("[Rust] json-serialize server starting on {}", addr);

    let listener = tokio::net::TcpListener::bind(addr)
        .await
        .expect("failed to bind");
    axum::serve(listener, app).await.expect("server error");
}
