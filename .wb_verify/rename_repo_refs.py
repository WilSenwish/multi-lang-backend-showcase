#!/usr/bin/env python3
"""把仓库内的旧名 multi-lang-backend-showcase 统一改为新名 multi-lang-backend-showcase。

默认干跑（只打印将要改动的行）；加位置参数 apply 才真正写盘。
跳过历史记录类文件（.wb_verify/all_logs/*、.wb_verify/*.log），它们记录的是改名前的运行现场。
"""
import os
import sys

OLD = "multi-lang-backend-showcase"
NEW = "multi-lang-backend-showcase"

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, ".."))

SKIP_DIRS = {".git", "node_modules", "target", "dist", "build", "__pycache__",
             "all_logs", "runs"}
SKIP_SUFFIX = (".log", ".lock", ".jar", ".class")
# 不要自替换（否则脚本里的 OLD 常量会被改掉）
SELF = os.path.basename(os.path.abspath(__file__))
# 二进制/大文件不碰
SIZE_LIMIT = 512 * 1024


def should_skip(path, name):
    if name == SELF:
        return True
    parts = set(os.path.relpath(path, REPO).split(os.sep))
    if parts & SKIP_DIRS:
        return True
    if name.endswith(SKIP_SUFFIX):
        return True
    return False


def main():
    apply = any(a.lstrip("-") == "apply" for a in sys.argv[1:])
    changed_files, total_hits = [], 0

    for root, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in sorted(files):
            path = os.path.join(root, name)
            if should_skip(path, name):
                continue
            try:
                if os.path.getsize(path) > SIZE_LIMIT:
                    continue
                with open(path, encoding="utf-8") as fh:
                    text = fh.read()
            except (UnicodeDecodeError, OSError):
                continue
            if OLD not in text:
                continue

            lines = text.split("\n")
            hits = [i + 1 for i, ln in enumerate(lines) if OLD in ln]
            rel = os.path.relpath(path, REPO)
            print(f"{rel}  ({len(hits)} 行)")
            for i in hits:
                print(f"    L{i}: {lines[i - 1].strip()[:110]}")

            if apply:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(text.replace(OLD, NEW))
                changed_files.append(rel)
            total_hits += len(hits)

    # .idea 下的 .iml 文件名本身含旧名（文件内容里没有），需同步改名
    iml_old = os.path.join(REPO, ".idea", OLD + ".iml")
    iml_new = os.path.join(REPO, ".idea", NEW + ".iml")
    if os.path.exists(iml_old):
        print(f"[.iml 改名] .idea/{OLD}.iml -> .idea/{NEW}.iml")
        if apply and not os.path.exists(iml_new):
            os.rename(iml_old, iml_new)

    print()
    print(f"命中文件 {len(changed_files) if apply else '?'} 个 / 行数 {total_hits}")
    if apply:
        print("已写入以下文件:")
        for f in changed_files:
            print("  " + f)
    else:
        print(">>> 干跑模式，未写盘。加位置参数 apply 执行。")


if __name__ == "__main__":
    main()
