//! 场景 03：命令行工具 — Rust 实现（简化版 wc，clap 参数解析）
//!
//! Rust CLI 工具特点（clap 是最主流的参数解析库）：
//! 1. clap 提供 derive 宏，参数定义即文档
//! 2. 编译成静态二进制，分发最方便（无运行时依赖）
//! 3. 启动速度 ~1ms（和 Go 相当）
//! 4. 二进制体积小（release + LTO + strip ≈ 2-5MB）
//! 5. 编译期参数校验（类型安全）
//!
//! 和 Java/Python 对比：
//! - Rust 编译慢（cargo 首次编译很痛苦），但运行时性能极致
//! - clap 参数解析 + 自动 help/version 比 Go flag 强、比 Python argparse 类型安全
//! - 和 Go 同为静态二进制分发，但 Rust 无 GC、启动快

use clap::Parser;
use std::fs;
use std::path::PathBuf;
use std::process;

/// 简化版 wc — 统计文件行数、词数、字符数
#[derive(Parser, Debug)]
#[command(
    name = "count",
    version = "1.0.0",
    about = "简化版 wc — 统计文件行数、词数、字符数",
    long_about = None,
)]
struct Cli {
    /// 只统计行数 (lines)
    #[arg(short = 'l', long = "lines")]
    show_lines: bool,

    /// 只统计词数 (words)
    #[arg(short = 'w', long = "words")]
    show_words: bool,

    /// 只统计字符数 (chars)
    #[arg(short = 'c', long = "chars")]
    show_chars: bool,

    /// 要统计的文件路径（支持多个）
    #[arg(required = true)]
    files: Vec<PathBuf>,
}

/// 统计单个文件的 (lines, words, chars)
fn count_file(path: &PathBuf) -> Result<(usize, usize, usize), String> {
    let content = fs::read_to_string(path)
        .map_err(|e| format!("读取 '{}' 失败: {}", path.display(), e))?;

    // 行数
    let lines = content.lines().count();

    // 词数：按空白分割
    let words = content.split_whitespace().count();

    // 字符数（Unicode 字符数，不是字节数）
    let chars = content.chars().count();

    Ok((lines, words, chars))
}

fn print_result(label: &str, lines: usize, words: usize, chars: usize,
                cli: &Cli) {
    let any_flag = cli.show_lines || cli.show_words || cli.show_chars;
    let default_all = !any_flag;

    let mut parts: Vec<String> = Vec::new();
    if cli.show_lines || default_all {
        parts.push(format!("lines={lines}"));
    }
    if cli.show_words || default_all {
        parts.push(format!("words={words}"));
    }
    if cli.show_chars || default_all {
        parts.push(format!("chars={chars}"));
    }

    let out = parts.join(" ");
    if label.is_empty() {
        println!("{out}");
    } else {
        println!("{out}  {label}");
    }
}

fn main() {
    let cli = Cli::parse();

    let mut total_l = 0usize;
    let mut total_w = 0usize;
    let mut total_c = 0usize;
    let multi = cli.files.len() > 1;

    for file in &cli.files {
        match count_file(file) {
            Ok((l, w, c)) => {
                if multi {
                    print_result(&file.display().to_string(), l, w, c, &cli);
                }
                total_l += l;
                total_w += w;
                total_c += c;
            }
            Err(e) => {
                eprintln!("count: {e}");
                process::exit(1);
            }
        }
    }

    if multi {
        eprintln!("---");
    }

    let label = if multi { "total" } else { "" };
    print_result(label, total_l, total_w, total_c, &cli);
}
