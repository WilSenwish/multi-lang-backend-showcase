//! 场景 14：数据分析处理 —— Rust 用 polars 做 group_by 聚合（性能王者）。
//!
//! 数据集与其它语言逐位一致：amount = LCG(i+1) 高 32 位 % 100000，category = i % categories。
//! 分位数统一 nearest-rank 口径（排序后取 ceil(p*n/100)-1 下标）：
//! polars 的 quantile 默认插值方式与 pandas 等各库不同，放任默认值必然跨语言对不齐，
//! 因此分位数与 Top-K 在原始数组上手写，分组聚合交给 polars（lazy API）。

use std::collections::HashMap;

use axum::http::StatusCode;
use axum::routing::{get, post};
use axum::{Json, Router};
use polars::prelude::*;
use serde::{Deserialize, Serialize};

const MULT: u64 = 6364136223846793005;
const INC: u64 = 1442695040888963407;
const AMOUNT_MOD: u64 = 100_000;
const PORT: u16 = 8143;

#[inline]
fn amount_of(i: u64) -> u64 {
    let h = (i + 1).wrapping_mul(MULT).wrapping_add(INC);
    (h >> 32) % AMOUNT_MOD
}

#[derive(Deserialize, Default)]
struct AnalyzeRequest {
    #[serde(default)]
    rows: Option<i64>,
    #[serde(default)]
    categories: Option<i64>,
}

#[derive(Serialize)]
struct GroupStat {
    category: String,
    count: i64,
    sum: i64,
    avg: f64,
    p50: i64,
    p95: i64,
}

#[derive(Serialize)]
struct TopRow {
    id: i64,
    category: String,
    amount: i64,
}

#[derive(Serialize)]
struct AnalyzeResponse {
    rows: i64,
    categories: i64,
    groups: Vec<GroupStat>,
    top10: Vec<TopRow>,
    gen_ms: i64,
    agg_ms: i64,
    elapsed_ms: i64,
}

/// nearest-rank 分位数：排序后取下标 ceil(p*n/100)-1（p 为整数百分位）。
fn nearest_rank(sorted: &[i64], p: usize) -> i64 {
    let n = sorted.len();
    let idx = ((p * n + 99) / 100).clamp(1, n);
    sorted[idx - 1]
}

fn bad_request(msg: &str) -> (StatusCode, Json<serde_json::Value>) {
    (
        StatusCode::BAD_REQUEST,
        Json(serde_json::json!({ "error": msg })),
    )
}

fn internal_error(e: PolarsError) -> (StatusCode, Json<serde_json::Value>) {
    (
        StatusCode::INTERNAL_SERVER_ERROR,
        Json(serde_json::json!({ "error": e.to_string() })),
    )
}

async fn health() -> Json<serde_json::Value> {
    Json(serde_json::json!({
        "service": "data-analysis", "lang": "rust", "engine": "polars",
    }))
}

async fn analyze(Json(req): Json<AnalyzeRequest>) -> Result<Json<AnalyzeResponse>, (StatusCode, Json<serde_json::Value>)> {
    let rows = req.rows.unwrap_or(200_000);
    let cats = req.categories.unwrap_or(8);
    if !(1_000..=2_000_000).contains(&rows) {
        return Err(bad_request("rows must be in [1000, 2000000]"));
    }
    if !(1..=64).contains(&cats) {
        return Err(bad_request("categories must be in [1, 64]"));
    }

    let t0 = std::time::Instant::now();

    // ---- 数据生成（保留原始数组供分位数 / Top-K 手写部分使用）----
    let n = rows as usize;
    let mut ids: Vec<i64> = Vec::with_capacity(n);
    let mut cat_idx: Vec<u32> = Vec::with_capacity(n);
    let mut amounts: Vec<i64> = Vec::with_capacity(n);
    for i in 0..n {
        ids.push(i as i64);
        cat_idx.push((i as i64 % cats) as u32);
        amounts.push(amount_of(i as u64) as i64);
    }

    // polars 0.5x 起 DataFrame::new 要求显式 height + Column 列表，且列名是 PlSmallStr；
    // 这里用 new_infer_height + Series::new 构造，避开版本间签名漂移。
    let df = DataFrame::new_infer_height(vec![
        Column::from(Series::new("id".into(), ids.clone())),
        Column::from(Series::new("category".into(), cat_idx.clone())),
        Column::from(Series::new("amount".into(), amounts.clone())),
    ])
    .map_err(internal_error)?;

    let t1 = std::time::Instant::now();

    // ---- 分组聚合：polars 一行流（lazy API，group_by + agg）----
    let grouped = df
        .clone()
        .lazy()
        .group_by([col("category")])
        // count 的输出类型是 IdxSize（随平台/版本可能是 u32 或 u64），统一 cast 到 Int64 再读，
        // 避免跨版本 dtype 漂移导致 .u32()/.u64() 取列失败。
        .agg([
            col("amount").count().cast(DataType::Int64).alias("cnt"),
            col("amount").sum().cast(DataType::Int64).alias("total"),
        ])
        .collect()
        .map_err(internal_error)?;

    // 读出聚合结果（组顺序不保证，稍后统一按 category 排序）
    let mut stat_map: HashMap<u32, (i64, i64)> = HashMap::with_capacity(cats as usize);
    let cat_col = grouped.column("category").map_err(internal_error)?.u32().map_err(internal_error)?;
    let cnt_col = grouped.column("cnt").map_err(internal_error)?.i64().map_err(internal_error)?;
    let sum_col = grouped.column("total").map_err(internal_error)?.i64().map_err(internal_error)?;
    for i in 0..grouped.height() {
        let cat = cat_col.get(i).unwrap_or(u32::MAX);
        let cnt = cnt_col.get(i).unwrap_or(0);
        let sum = sum_col.get(i).unwrap_or(0);
        stat_map.insert(cat, (cnt, sum));
    }

    // ---- 分位数 / Top-K：统一 nearest-rank / 字典序口径，手写 ----
    let mut buckets: Vec<Vec<i64>> = vec![Vec::new(); cats as usize];
    for i in 0..n {
        buckets[cat_idx[i] as usize].push(amounts[i]);
    }
    let mut groups: Vec<GroupStat> = Vec::with_capacity(cats as usize);
    for (c, mut vals) in buckets.into_iter().enumerate() {
        if vals.is_empty() {
            continue;
        }
        let (cnt, sum) = stat_map.get(&(c as u32)).copied().unwrap_or((0, 0));
        vals.sort_unstable();
        groups.push(GroupStat {
            category: format!("cat-{}", c),
            count: cnt,
            sum,
            avg: sum as f64 / cnt as f64,
            p50: nearest_rank(&vals, 50),
            p95: nearest_rank(&vals, 95),
        });
    }
    groups.sort_by(|a, b| a.category.cmp(&b.category));

    // Top-10：amount 降序，id 升序
    let mut order: Vec<usize> = (0..n).collect();
    order.sort_by(|&a, &b| amounts[b].cmp(&amounts[a]).then_with(|| ids[a].cmp(&ids[b])));
    let top10: Vec<TopRow> = order
        .into_iter()
        .take(10)
        .map(|i| TopRow {
            id: ids[i],
            category: format!("cat-{}", cat_idx[i]),
            amount: amounts[i],
        })
        .collect();

    let t2 = std::time::Instant::now();
    Ok(Json(AnalyzeResponse {
        rows,
        categories: cats,
        groups,
        top10,
        gen_ms: t1.duration_since(t0).as_millis() as i64,
        agg_ms: t2.duration_since(t1).as_millis() as i64,
        elapsed_ms: t2.duration_since(t0).as_millis() as i64,
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

    let app = Router::new().route("/health", get(health)).route("/analyze", post(analyze));

    let addr = format!("0.0.0.0:{}", PORT);
    tracing::info!(addr = %addr, "server starting");
    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    axum::serve(listener, app).await.unwrap();
}
