//! 场景 06：轻量 RAG Demo — Rust 实现 (axum + 内存向量存储)
//!
//! Rust 版本特点：
//! 1. 和 Java/Go/Python 完全相同的 pipeline
//! 2. Rust 的无 GC 特性让向量计算（纯 CPU）性能极佳
//! 3. 正则、字符串处理都非常快
//! 4. Result 强制错误处理，不会漏异常

use axum::{
    body::Bytes,
    extract::State,
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::{get, post},
    Json as AxumJson, Router,
};
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;
use std::fs;
use std::path::Path;
use std::sync::{Mutex, OnceLock};

// ==================== 数据结构 ====================

#[derive(Debug, Clone)]
struct Chunk {
    id: String,
    text: String,
    source: String,
    vector: Vec<f64>,
}

struct RagStore {
    chunks: Mutex<Vec<Chunk>>,
    vocab: Mutex<Vec<String>>,
}

impl RagStore {
    fn new() -> Self {
        Self {
            chunks: Mutex::new(Vec::new()),
            vocab: Mutex::new(Vec::new()),
        }
    }

    // ---- 摄入 ----

    fn ingest_file(&self, file_path: &str) -> Result<usize, String> {
        let p = Path::new(file_path);
        if !p.exists() {
            return Err(format!("文件不存在: {}", file_path));
        }

        let content = fs::read_to_string(p).map_err(|e| e.to_string())?;
        let file_name = p
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or("unknown")
            .to_string();

        // 按空行切段落（与 Go/Python/Java/TS 同款正则：\n\s*\n，
        // 之前的 "\n\n" 字面切分会把 "\n \n" 这类分隔符漏掉，导致 chunk 数不一致）
        let para_re = para_split_re();
        let mut chunks = self.chunks.lock().unwrap();
        chunks.clear();

        let mut idx = 0;
        for para in para_re.split(&content) {
            let trimmed = para.trim();
            if trimmed.chars().count() < 10 {
                continue;
            }
            let id = format!("{}#{}", file_name, idx);
            chunks.push(Chunk {
                id,
                text: trimmed.to_string(),
                source: file_name.clone(),
                vector: vec![],
            });
            idx += 1;
        }

        drop(chunks);
        self.rebuild_vectors();
        Ok(idx)
    }

    fn rebuild_vectors(&self) {
        // 收集所有词
        let mut vocab_set: BTreeSet<String> = BTreeSet::new();
        {
            let chunks = self.chunks.lock().unwrap();
            for c in chunks.iter() {
                for w in tokenize(&c.text) {
                    vocab_set.insert(w);
                }
            }
        }

        let vocab: Vec<String> = vocab_set.into_iter().collect();

        // 给每个 chunk 生成向量
        {
            let mut chunks = self.chunks.lock().unwrap();
            for c in chunks.iter_mut() {
                c.vector = build_vector(&c.text, &vocab);
            }
        }

        {
            let mut v = self.vocab.lock().unwrap();
            *v = vocab;
        }
    }

    // ---- 检索 ----

    fn search(&self, question: &str, top_k: usize) -> Vec<SourceResult> {
        let chunks = self.chunks.lock().unwrap();
        let vocab = self.vocab.lock().unwrap();

        if vocab.is_empty() {
            return Vec::new();
        }

        let q_vec = build_vector(question, &vocab);
        let mut results: Vec<SourceResult> = Vec::new();

        for c in chunks.iter() {
            let score = cosine_similarity(&q_vec, &c.vector);
            if score > 0.0 {
                results.push(SourceResult {
                    text: c.text.clone(),
                    source: c.source.clone(),
                    score: (score * 10000.0).round() / 10000.0,
                });
            }
        }

        results.sort_by(|a, b| b.score.partial_cmp(&a.score).unwrap_or(std::cmp::Ordering::Equal));
        results.truncate(top_k);
        results
    }

    // ---- 状态 ----

    fn chunk_count(&self) -> usize {
        self.chunks.lock().unwrap().len()
    }

    fn vocab_size(&self) -> usize {
        self.vocab.lock().unwrap().len()
    }
}

// ==================== 辅助函数 ====================

/// 段落切分正则（进程内只编译一次）
fn para_split_re() -> &'static regex::Regex {
    static RE: OnceLock<regex::Regex> = OnceLock::new();
    RE.get_or_init(|| regex::Regex::new(r"\n\s*\n").unwrap())
}

fn tokenize(text: &str) -> Vec<String> {
    let lower = text.to_lowercase();
    let mut tokens = Vec::new();
    let mut current = String::new();

    // 字符类与其余四门的正则 [^a-z0-9\u4e00-\u9fff] 严格对齐：
    // 之前的 is_alphanumeric() 是 Unicode 全集（é/Ω 等都算），会把词表与向量算得不一样
    for ch in lower.chars() {
        if ch.is_ascii_alphanumeric() || ('\u{4e00}'..='\u{9fff}').contains(&ch) {
            current.push(ch);
        } else {
            if current.chars().count() >= 2 {
                tokens.push(std::mem::take(&mut current));
            } else {
                current.clear();
            }
        }
    }
    if current.chars().count() >= 2 {
        tokens.push(current);
    }
    tokens
}

fn build_vector(text: &str, vocab: &[String]) -> Vec<f64> {
    let tokens = tokenize(text);
    let mut freq = std::collections::HashMap::new();
    for t in tokens {
        *freq.entry(t).or_insert(0u64) += 1;
    }
    vocab.iter()
        .map(|w| *freq.get(w).unwrap_or(&0) as f64)
        .collect()
}

fn cosine_similarity(a: &[f64], b: &[f64]) -> f64 {
    let (mut dot, mut norm_a, mut norm_b) = (0.0f64, 0.0f64, 0.0f64);
    for i in 0..a.len() {
        dot += a[i] * b[i];
        norm_a += a[i] * a[i];
        norm_b += b[i] * b[i];
    }
    if norm_a == 0.0 || norm_b == 0.0 {
        return 0.0;
    }
    dot / (norm_a.sqrt() * norm_b.sqrt())
}

fn mock_answer(question: &str, sources: &[SourceResult]) -> String {
    if sources.is_empty() {
        return "我没有找到相关信息，请先 POST /ingest 摄入文档。".to_string();
    }
    let mut sb = format!("根据摄入的文档，关于「{}」的相关内容：\n\n", question);
    for (i, s) in sources.iter().enumerate() {
        // {:.4} 与 Go 的 %.4f / Python 的 :.4f / TS 的 toFixed(4) / Java 的 %.4f 对齐
        // （f64 默认 Display 会把 1.0 渲染成 "1"，与其余四门不一致）
        sb.push_str(&format!(
            "{}. (来自 {}, 相关度 {:.4}) {}\n",
            i + 1,
            s.source,
            s.score,
            s.text
        ));
    }
    sb
}

// ==================== API 结构 ====================

#[derive(Deserialize)]
struct IngestReq {
    file_path: String,
}

#[derive(Deserialize)]
struct AskReq {
    question: String,
    /// 缺省 None → 默认 3；显式传值（含 0）必须 >= 1，与其余四门一致
    #[serde(default)]
    top_k: Option<usize>,
}

/// 400 响应（统一契约：畸形 JSON / 缺字段 / 类型错误 / 非法值都走这里）
fn bad_request(msg: &str) -> Response {
    (
        StatusCode::BAD_REQUEST,
        AxumJson(serde_json::json!({"success": false, "error": msg})),
    )
        .into_response()
}

#[derive(Serialize, Clone)]
struct SourceResult {
    text: String,
    source: String,
    score: f64,
}

// ==================== Handlers ====================

type AppState = std::sync::Arc<RagStore>;

async fn ingest(State(store): State<AppState>, body: Bytes) -> Response {
    // 手动解析而非 axum 的 Json 提取器：后者对"语法错误"给 400、对"类型错误"给 422，
    // 与其余四门不一致；这里统一映射为 400（契约：非法入参一律 400）。
    let req: IngestReq = match serde_json::from_slice(&body) {
        Ok(r) => r,
        Err(e) => return bad_request(&format!("invalid request body: {e}")),
    };

    match store.ingest_file(&req.file_path) {
        Ok(chunks) => {
            let vocab_size = store.vocab_size();
            AxumJson(serde_json::json!({
                "success": true,
                "file": req.file_path,
                "chunks": chunks,
                "embeddings_generated": chunks,
                "vocab_size": vocab_size,
            }))
            .into_response()
        }
        Err(e) => {
            // 文件不存在/是目录/权限问题都是客户端给的 path 不对 → 400
            bad_request(&e)
        }
    }
}

async fn ask(State(store): State<AppState>, body: Bytes) -> Response {
    let req: AskReq = match serde_json::from_slice(&body) {
        Ok(r) => r,
        Err(e) => return bad_request(&format!("invalid request body: {e}")),
    };
    let top_k = match req.top_k {
        None => 3,
        Some(k) if k >= 1 => k,
        Some(_) => return bad_request("top_k must be >= 1"),
    };

    let sources = store.search(&req.question, top_k);
    let answer = mock_answer(&req.question, &sources);

    AxumJson(serde_json::json!({
        "success": true,
        "question": req.question,
        "answer": answer,
        "sources": sources,
        "mode": "local-mock",
    }))
    .into_response()
}

async fn health(State(store): State<AppState>) -> Response {
    AxumJson(serde_json::json!({
        "service": "simple-rag-rust",
        "chunks_loaded": store.chunk_count(),
        "vocab_size": store.vocab_size(),
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

    let store = std::sync::Arc::new(RagStore::new());

    let app = Router::new()
        .route("/ingest", post(ingest))
        .route("/ask", post(ask))
        .route("/health", get(health))
        .with_state(store);

    let addr = "0.0.0.0:8103";
    tracing::info!(addr = %addr, "server starting");

    let listener = tokio::net::TcpListener::bind(addr)
        .await
        .expect("failed to bind");
    axum::serve(listener, app).await.expect("server error");
}
