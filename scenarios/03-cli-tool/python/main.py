"""
场景 03：命令行工具 — Python 实现（简化版 wc）

Python CLI 工具特点：
1. 标准库 argparse 功能强（子命令、互斥组等）
2. 直接 python main.py 就能跑，不需要编译
3. 但性能不如编译型语言，分发需要 Python 环境
4. PyInstaller 可以打包成单文件二进制，但体积大（50-100MB+）

和 Go/Rust 原生二进制对比：
- Python 是解释执行，运行时需要 Python 解释器
- 参数解析 argparse 比 Go flag 功能强很多
- 启动速度 ~50-200ms（比 Java 快，比 Go/Rust 慢）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def count_file(path: str) -> tuple[int, int, int]:
    """统计单个文件的 (lines, words, chars)"""
    try:
        content = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"count: 无法打开 '{path}': 文件不存在", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        print(f"count: 读取 '{path}' 失败: {e}", file=sys.stderr)
        sys.exit(1)

    # 行数
    lines = content.count("\n")
    if content and not content.endswith("\n"):
        lines += 1
    elif content == "":
        lines = 0

    # 词数：按空白分割
    words = len(content.split())

    # 字符数
    chars = len(content)

    return lines, words, chars


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="count",
        description="简化版 wc — 统计文件行数、词数、字符数",
        add_help=True,
    )
    parser.add_argument("-l", dest="show_lines", action="store_true", help="只统计行数 (lines)")
    parser.add_argument("-w", dest="show_words", action="store_true", help="只统计词数 (words)")
    parser.add_argument("-c", dest="show_chars", action="store_true", help="只统计字符数 (chars)")
    parser.add_argument("files", nargs="+", help="要统计的文件路径（支持多个）")
    return parser


def print_result(label: str, lines: int, words: int, chars: int,
                 show_l: bool, show_w: bool, show_c: bool, default_all: bool):
    parts = []
    if show_l or default_all:
        parts.append(f"lines={lines}")
    if show_w or default_all:
        parts.append(f"words={words}")
    if show_c or default_all:
        parts.append(f"chars={chars}")

    out = " ".join(parts)
    if label:
        print(f"{out}  {label}")
    else:
        print(out)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    show_l = args.show_lines
    show_w = args.show_words
    show_c = args.show_chars
    any_flag = show_l or show_w or show_c
    default_all = not any_flag

    total_l = total_w = total_c = 0
    multi = len(args.files) > 1

    for f in args.files:
        l, w, c = count_file(f)
        if multi:
            print_result(f, l, w, c, show_l, show_w, show_c, default_all)
        total_l += l
        total_w += w
        total_c += c

    if multi:
        print("---")

    label = "total" if multi else ""
    print_result(label, total_l, total_w, total_c, show_l, show_w, show_c, default_all)


if __name__ == "__main__":
    main()
