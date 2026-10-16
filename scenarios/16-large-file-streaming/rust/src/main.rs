//! 场景 16：大文件流式处理 —— Rust 用固定缓冲 + 手写行边界处理。
//!
//! 语义契约（五门语言必须逐字一致，见场景 README）：
//!   1. 生成一个确定性的定长行文件（每行 10 字节：`NNN,AAAAA\n`），生成过程本身也是流式的
//!   2. 以 `chunk_kib × 1024` 字节的固定缓冲读取，**绝不整体读入内存**
//!   3. 行可能跨越 chunk 边界 → 用"残余行拼接"处理，不能假设 chunk 边界 = 行边界
//!   4. 逐行解析 amount，过滤 `amount >= min_amount`，输出 `NNN,BBBBBB\n`（11 字节），流式写
//!   5. 输入/输出各算一份 SHA-256（取前 8 字节 hex），处理完删除两个临时文件
//!
//! Rust 的取舍：
//!   - `&[u8]` 切片解析让"零每行分配"成为默认值 —— 不需要为了性能改写代码
//!   - `#[global_allocator]` 可以精确统计堆分配峰值（别的语言只能拿到"运行时估计"）
//!   - 代价：同样要手写行边界与数字解析；`Read::read` 不保证读满，得自己循环

use std::alloc::{GlobalAlloc, Layout, System};
use std::fs::File;
use std::io::{Read, Write};
use std::path::PathBuf;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::Instant;

use axum::http::StatusCode;
use axum::routing::post;
use axum::{Json, Router};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

const PORT: u16 = 8153;
/// 确定性数据序列：h(i) = (i+1)*MULT + INC（mod 2^64），amount = (h >> 32) % 100000
const MULT: u64 = 6364136223846793005;
const INC: u64 = 1442695040888963407;
const LINE_IN: usize = 10; // "%03d,%05d\n"
const LINE_OUT: usize = 11; // "%03d,%06d\n"
const GEN_BUF: usize = 64 * 1024;

// ---- 自定义全局分配器：精确统计"堆分配峰值" --------------------------------
// 这是 Rust 在本场景的独家优势：其它四门语言只能拿到运行时给出的估计值或采样值，
// Rust 可以在分配器层面拿到逐字节的真实数字。
static ALLOC_CUR: AtomicUsize = AtomicUsize::new(0);
static ALLOC_PEAK: AtomicUsize = AtomicUsize::new(0);

struct TrackingAlloc;

unsafe impl GlobalAlloc for TrackingAlloc {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        let ptr = System.alloc(layout);
        if !ptr.is_null() {
            let cur = ALLOC_CUR.fetch_add(layout.size(), Ordering::Relaxed) + layout.size();
            ALLOC_PEAK.fetch_max(cur, Ordering::Relaxed);
        }
        ptr
    }
    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        let ptr = System.alloc_zeroed(layout);
        if !ptr.is_null() {
            let cur = ALLOC_CUR.fetch_add(layout.size(), Ordering::Relaxed) + layout.size();
            ALLOC_PEAK.fetch_max(cur, Ordering::Relaxed);
        }
        ptr
    }
    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        ALLOC_CUR.fetch_sub(layout.size(), Ordering::Relaxed);
        System.dealloc(ptr, layout)
    }
    unsafe fn realloc(&self, ptr: *mut u8, layout: Layout, new_size: usize) -> *mut u8 {
        // 先减旧再加新：中间态可能短暂偏低，但峰值统计不受影响
        ALLOC_CUR.fetch_sub(layout.size(), Ordering::Relaxed);
        let p = System.realloc(ptr, layout, new_size);
        if !p.is_null() {
            let cur = ALLOC_CUR.fetch_add(new_size, Ordering::Relaxed) + new_size;
            ALLOC_PEAK.fetch_max(cur, Ordering::Relaxed);
        } else {
            ALLOC_CUR.fetch_add(layout.size(), Ordering::Relaxed);
        }
        p
    }
}

#[global_allocator]
static ALLOC: TrackingAlloc = TrackingAlloc;

fn heap_peak_bytes() -> i64 {
    ALLOC_PEAK.load(Ordering::Relaxed) as i64
}

/// 进程 RSS 峰值（ru_maxrss）：Linux 单位为 KB，macOS 为 bytes。
fn rss_bytes() -> i64 {
    unsafe {
        let mut ru: libc::rusage = std::mem::zeroed();
        if libc::getrusage(libc::RUSAGE_SELF, &mut ru) != 0 {
            return -1;
        }
        if cfg!(target_os = "macos") {
            ru.ru_maxrss
        } else {
            ru.ru_maxrss * 1024
        }
    }
}

// ---- 工具：手写定宽数字（零分配） ----------------------------------------
fn push_fixed(buf: &mut Vec<u8>, v: u32, width: usize) {
    let pos = buf.len();
    for _ in 0..width {
        buf.push(b'0');
    }
    let mut v = v;
    for k in (0..width).rev() {
        buf[pos + k] = b'0' + (v % 10) as u8;
        v /= 10;
    }
}

fn push_line_in(buf: &mut Vec<u8>, i: u64, amount: u32) {
    let g = (i % 1000) as u32;
    buf.push(b'0' + (g / 100) as u8);
    buf.push(b'0' + ((g / 10) % 10) as u8);
    buf.push(b'0' + (g % 10) as u8);
    buf.push(b',');
    push_fixed(buf, amount, 5);
    buf.push(b'\n');
}

// ---- 阶段一：流式生成源文件 ----------------------------------------------
fn generate(path: &PathBuf, lines: u64) -> std::io::Result<()> {
    let mut f = File::create(path)?;
    let mut buf: Vec<u8> = Vec::with_capacity(GEN_BUF);
    let mut h = INC;
    for i in 0..lines {
        h = h.wrapping_add(MULT);
        let amount = ((h >> 32) % 100000) as u32;
        push_line_in(&mut buf, i, amount);
        if buf.len() + LINE_IN > GEN_BUF {
            f.write_all(&buf)?;
            buf.clear();
        }
    }
    if !buf.is_empty() {
        f.write_all(&buf)?;
    }
    Ok(())
}

/// 读满整个 buf 或遇到 EOF。`Read::read` 不保证读满，必须自己循环。
fn fill_chunk<R: Read>(r: &mut R, buf: &mut [u8]) -> std::io::Result<usize> {
    let mut total = 0usize;
    while total < buf.len() {
        match r.read(&mut buf[total..])? {
            0 => break,
            n => total += n,
        }
    }
    Ok(total)
}

#[derive(Serialize)]
struct StreamResponse {
    lang: String,
    size_mb: usize,
    chunk_kib: usize,
    min_amount: u32,
    bytes_read: u64,
    lines_read: u64,
    bytes_written: u64,
    lines_written: u64,
    output_file_bytes: i64,
    checksum: String,
    output_checksum: String,
    chunks: u64,
    gen_ms: u64,
    proc_ms: u64,
    elapsed_ms: u64,
    throughput_mb_s: f64,
    rss_before_bytes: i64,
    rss_peak_bytes: i64,
    rss_delta_bytes: i64,
    peak_heap_bytes: i64,
    heap_metric: String,
    cleanup: bool,
}

#[derive(Deserialize)]
struct StreamRequest {
    size_mb: Option<usize>,
    chunk_kib: Option<usize>,
    min_amount: Option<u32>,
}

// ---- 阶段二：流式处理（读 → 解析 → 过滤 → 转换 → 写） -------------------
fn process(
    src: &PathBuf,
    dst: &PathBuf,
    chunk: usize,
    min_amount: u32,
    size_mb: usize,
    chunk_kib: usize,
) -> std::io::Result<StreamResponse> {
    let mut input = File::open(src)?;
    let mut output = File::create(dst)?;
    let mut h_in = Sha256::new();
    let mut h_out = Sha256::new();

    let mut buf = vec![0u8; chunk];
    // pending 保存"上一个 chunk 剩下的半行"，容量固定 → 内存与文件大小无关
    let mut pending: Vec<u8> = Vec::with_capacity(chunk + LINE_IN);
    let mut out_buf: Vec<u8> = Vec::with_capacity(chunk + LINE_OUT);

    let mut bytes_read = 0u64;
    let mut lines_read = 0u64;
    let mut bytes_written = 0u64;
    let mut lines_written = 0u64;
    let mut chunks = 0u64;

    let t0 = Instant::now();
    loop {
        let n = fill_chunk(&mut input, &mut buf)?;
        if n == 0 {
            break;
        }
        chunks += 1;
        bytes_read += n as u64;
        h_in.update(&buf[..n]);
        pending.extend_from_slice(&buf[..n]);

        let mut start = 0usize;
        for i in 0..pending.len() {
            if pending[i] != b'\n' {
                continue;
            }
            lines_read += 1;
            if i - start >= LINE_IN - 1 {
                let mut amount: u32 = 0;
                for k in start + 4..start + 9 {
                    amount = amount * 10 + (pending[k] - b'0') as u32;
                }
                if amount >= min_amount {
                    out_buf.extend_from_slice(&pending[start..start + 4]); // "%03d," 原样拷贝
                    push_fixed(&mut out_buf, amount * 2, 6);
                    out_buf.push(b'\n');
                    lines_written += 1;
                    bytes_written += LINE_OUT as u64;
                    if out_buf.len() + LINE_OUT > out_buf.capacity() {
                        h_out.update(&out_buf);
                        output.write_all(&out_buf)?;
                        out_buf.clear();
                    }
                }
            }
            start = i + 1;
        }
        if start > 0 {
            pending.drain(..start);
        }
        if n < chunk {
            break; // 没读满 = EOF
        }
    }
    if !out_buf.is_empty() {
        h_out.update(&out_buf);
        output.write_all(&out_buf)?;
    }
    let secs = t0.elapsed().as_secs_f64();

    Ok(StreamResponse {
        lang: "rust".to_string(),
        size_mb,
        chunk_kib,
        min_amount,
        bytes_read,
        lines_read,
        bytes_written,
        lines_written,
        output_file_bytes: -1,
        checksum: hex8(h_in.finalize()),
        output_checksum: hex8(h_out.finalize()),
        chunks,
        gen_ms: 0,
        proc_ms: t0.elapsed().as_millis() as u64,
        elapsed_ms: 0,
        throughput_mb_s: if secs > 0.0 {
            bytes_read as f64 / (1024.0 * 1024.0) / secs
        } else {
            0.0
        },
        rss_before_bytes: 0,
        rss_peak_bytes: 0,
        rss_delta_bytes: 0,
        peak_heap_bytes: heap_peak_bytes(),
        heap_metric: "rust.global_allocator 精确统计（堆分配峰值，非采样）".to_string(),
        cleanup: false,
    })
}

fn hex8(d: sha2::digest::Output<Sha256>) -> String {
    d.iter().take(8).map(|b| format!("{:02x}", b)).collect()
}

fn clamp(v: usize, lo: usize, hi: usize) -> usize {
    v.clamp(lo, hi)
}

/// 同步阻塞的处理逻辑（文件 IO 密集），放进 spawn_blocking 避免堵住 tokio 的工作线程。
fn run(req: StreamRequest) -> std::io::Result<StreamResponse> {
    let size_mb = clamp(req.size_mb.unwrap_or(32), 1, 512);
    let chunk_kib = clamp(req.chunk_kib.unwrap_or(64), 1, 4096);
    let min_amount = req.min_amount.unwrap_or(50000).min(99999);

    let lines = size_mb as u64 * 1024 * 1024 / LINE_IN as u64;
    let tag = format!(
        "stream16-{}-{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_nanos())
            .unwrap_or(0)
    );
    let src = std::env::temp_dir().join(format!("{}.in", tag));
    let dst = std::env::temp_dir().join(format!("{}.out", tag));

    let rss_before = rss_bytes();
    let t_all = Instant::now();

    generate(&src, lines)?;
    let gen_ms = t_all.elapsed().as_millis() as u64;

    let mut res = match process(&src, &dst, chunk_kib * 1024, min_amount, size_mb, chunk_kib) {
        Ok(r) => r,
        Err(e) => {
            let _ = std::fs::remove_file(&src);
            let _ = std::fs::remove_file(&dst);
            return Err(e);
        }
    };

    // 真实写出的字节数（stat 文件，而不是信任计数器）—— 计数器可能与真实写入脱节
    res.output_file_bytes = std::fs::metadata(&dst).map(|m| m.len() as i64).unwrap_or(-1);

    // 清理临时文件：不删的话多跑几次就把磁盘撑满了
    let existed = src.exists();
    let _ = std::fs::remove_file(&src);
    let _ = std::fs::remove_file(&dst);
    res.cleanup = existed && !src.exists() && !dst.exists();

    res.gen_ms = gen_ms;
    res.elapsed_ms = t_all.elapsed().as_millis() as u64;
    res.rss_before_bytes = rss_before;
    res.rss_peak_bytes = rss_bytes();
    res.rss_delta_bytes = res.rss_peak_bytes - res.rss_before_bytes;
    Ok(res)
}

async fn handler(Json(req): Json<StreamRequest>) -> Result<Json<StreamResponse>, (StatusCode, String)> {
    tokio::task::spawn_blocking(move || run(req))
        .await
        .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, format!("task panic: {}", e)))?
        .map(Json)
        .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, format!("io error: {}", e)))
}

#[tokio::main]
async fn main() {
    let app = Router::new().route("/stream/process", post(handler));
    let addr = format!("0.0.0.0:{}", PORT);
    println!("large-file-streaming (rust) listening on {}", addr);
    let listener = tokio::net::TcpListener::bind(&addr).await.unwrap();
    axum::serve(listener, app).await.unwrap();
}
