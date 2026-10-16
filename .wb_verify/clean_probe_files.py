#!/usr/bin/env python3
"""清理沙箱写权限探测遗留的探针文件（随机名 + 内容恒为 4 字节 `blat`）。

判据（三条同时满足才删，避免误删）:
  1. 是普通文件（非目录/符号链接）
  2. 文件名是随机串（长度 >= 6，仅含字母/数字/下划线，且不是常规文件名）
  3. 内容 strip() 后恰好等于 b"blat"，且体积 <= 8 字节
默认只扫描并报告；加 --apply 才真正删除。
"""
from __future__ import annotations

import glob
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {".git", ".idea", "target", "dist", "__pycache__", ".venv", "venv"}
PROBE = b"blat"


def is_probe(path: str) -> bool:
    name = os.path.basename(path)
    if name.startswith(".") or len(name) < 6:
        return False
    if not name.replace("_", "").isalnum():
        return False
    if not os.path.isfile(path) or os.path.islink(path):
        return False
    try:
        if os.path.getsize(path) > 8:
            return False
        with open(path, "rb") as f:
            return f.read().strip() == PROBE
    except OSError:
        return False


def scan() -> list[str]:
    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            p = os.path.join(dirpath, fn)
            if is_probe(p):
                found.append(p)
    return sorted(found)


def main() -> None:
    apply = any(a.lstrip("-") == "apply" for a in sys.argv[1:])
    found = scan()
    print("扫描根目录: %s" % ROOT)
    print("命中探针文件: %d 个" % len(found))
    for p in found:
        print("  %s  (%d bytes)" % (os.path.relpath(p, ROOT), os.path.getsize(p)))
    if not found:
        print("无需清理。")
        return
    if not apply:
        print("\n[DRY-RUN] 未删除任何文件；加 --apply 执行删除。")
        return
    ok = 0
    for p in found:
        if is_probe(p):  # 删除前复查，防止 TOCTOU
            os.remove(p)
            ok += 1
    print("\n已删除 %d 个探针文件。" % ok)


if __name__ == "__main__":
    main()
