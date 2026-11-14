//! 场景 04：文件读写 & 目录遍历 — Rust 实现 (axum + std::fs)
//!
//! Rust 文件 IO 特点：
//! 1. std::fs 同步，tokio::fs 异步
//! 2. walkdir crate 做递归遍历（比自己写递归安全）
//! 3. Path / PathBuf 处理路径（和 Go filepath 类似）
//! 4. 创建目录用 create_dir_all（自动处理不存在的父目录）
//! 5. 错误处理用 Result，必须处理（编译器不让你忽略）
//!
//! 和 Java/Go/Python 对比：
//! - Rust 错误处理最严格，编译器强制处理
//! - Rust 没有 nil pointer 安全问题，文件操作的错误必须显式处理
//! - 同步 std::fs 也很快（Rust 本身就快）

use axum::{
    extract::{Query, State, Json as AxumJson},
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::{get, post},
    Router,
};
use serde::{Deserialize, Serialize};
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};

// ==================== 结构体 ====================

#[derive(Deserialize)]
struct WriteReq {
    path: String,
    content: serde_json::Value,
    #[serde(default)]
    append: bool,
}

#[derive(Deserialize)]
struct ReadQuery {
    path: String,
}

#[derive(Deserialize)]
struct ScanQuery {
    dir: String,
    #[serde(default = "default_true")]
    recursive: bool,
}

fn default_true() -> bool { true }

// ==================== 3 个 Handler ====================

async fn write(State(_): State<()>, AxumJson(req): AxumJson<WriteReq>) -> Response {
    let path = Path::new(&req.path);
    if let Some(parent) = path.parent() {
        if !parent.as_os_str().is_empty() {
            // 创建父目录失败不算 5xx：与其余四门一致，
            // 统一用 200 + success:false 表达"这次写没成功"，错误详情放 body
            if let Err(e) = fs::create_dir_all(parent) {
                return ok_resp(serde_json::json!({
                    "success": false,
                    "error": format!("创建目录失败: {e}")
                }));
            }
        }
    }

    // content 转字符串
    let content = match &req.content {
        serde_json::Value::String(s) => s.clone(),
        other => serde_json::to_string(other).unwrap_or_else(|_| other.to_string()),
    };

    let result = if req.append {
        // OpenOptions 追加模式
        fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(path)
            .and_then(|mut f| f.write_all(content.as_bytes()))
    } else {
        fs::write(path, content.as_bytes())
    };

    match result {
        Ok(_) => ok_resp(serde_json::json!({
            "success": true,
            "path": req.path,
            "bytes_written": content.len(),
            "append": req.append,
        })),
        // 写失败 → 200 + success:false（曾经这里是 500，与其余四门不一致）
        Err(e) => ok_resp(serde_json::json!({
            "success": false,
            "error": e.to_string()
        })),
    }
}

async fn read(State(_): State<()>, Query(q): Query<ReadQuery>) -> Response {
    // 统一契约：path 缺失/为空串 → 400
    if q.path.is_empty() {
        return (StatusCode::BAD_REQUEST, "missing path param").into_response();
    }
    let path = Path::new(&q.path);
    if !path.exists() {
        return (StatusCode::NOT_FOUND, format!("文件不存在: {}", q.path)).into_response();
    }
    if !path.is_file() {
        return (StatusCode::BAD_REQUEST, format!("不是文件: {}", q.path)).into_response();
    }

    match fs::read_to_string(path) {
        Ok(content) => {
            let bytes = content.as_bytes().len();
            ok_resp(serde_json::json!({
                "path": q.path,
                "content": content,
                "bytes": bytes,
            }))
        }
        Err(e) => (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()).into_response(),
    }
}

async fn scan(State(_): State<()>, Query(q): Query<ScanQuery>) -> Response {
    // 统一契约：dir 缺失/为空串 → 400
    if q.dir.is_empty() {
        return (StatusCode::BAD_REQUEST, "missing dir param").into_response();
    }
    let start = Path::new(&q.dir);
    if !start.exists() {
        return (StatusCode::NOT_FOUND, format!("目录不存在: {}", q.dir)).into_response();
    }
    if !start.is_dir() {
        return (StatusCode::BAD_REQUEST, format!("不是目录: {}", q.dir)).into_response();
    }

    let file_count;
    let total_bytes;

    if q.recursive {
        // 递归：walk through all entries
        let mut fc = 0u64;
        let mut tb = 0u64;
        walk_recursive(start, &mut fc, &mut tb);
        file_count = fc;
        total_bytes = tb;
    } else {
        match fs::read_dir(start) {
            Ok(entries) => {
                let mut fc = 0u64;
                let mut tb = 0u64;
                for entry in entries.flatten() {
                    if entry.path().is_file() {
                        if let Ok(meta) = entry.metadata() {
                            fc += 1;
                            tb += meta.len();
                        }
                    }
                }
                file_count = fc;
                total_bytes = tb;
            }
            Err(e) => return err_resp(e.to_string()),
        }
    }

    ok_resp(serde_json::json!({
        "dir": q.dir,
        "recursive": q.recursive,
        "files": file_count,
        "total_bytes": total_bytes,
    }))
}

/// 递归遍历目录（手动实现，避免额外依赖）
fn walk_recursive(dir: &Path, fc: &mut u64, tb: &mut u64) {
    if let Ok(entries) = fs::read_dir(dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_dir() {
                walk_recursive(&path, fc, tb);
            } else if path.is_file() {
                if let Ok(meta) = entry.metadata() {
                    *fc += 1;
                    *tb += meta.len();
                }
            }
        }
    }
}

// ==================== 辅助 ====================

fn ok_resp(data: serde_json::Value) -> Response {
    (StatusCode::OK, AxumJson(data)).into_response()
}

fn err_resp(msg: String) -> Response {
    (StatusCode::INTERNAL_SERVER_ERROR, AxumJson(serde_json::json!({"success": false, "error": msg}))).into_response()
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

    let app = Router::new()
        .route("/file/write", post(write))
        .route("/file/read", get(read))
        .route("/file/scan", get(scan))
        .with_state(());

    let addr = "0.0.0.0:8098";
    tracing::info!(addr = %addr, "server starting");

    let listener = tokio::net::TcpListener::bind(addr)
        .await
        .expect("failed to bind");
    axum::serve(listener, app).await.expect("server error");
}
