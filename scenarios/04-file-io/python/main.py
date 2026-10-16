"""
场景 04：文件读写 & 目录遍历 — Python 实现 (FastAPI + pathlib)

Python 文件 IO 特点：
1. pathlib 是现代 Python 的标准做法（面向对象的 Path）
2. os.path 是旧式做法（函数式）
3. 文件读写用 pathlib.Path.read_text / write_text
4. 目录遍历：pathlib.Path.rglob("*") 递归，iterdir() 非递归
5. 编码处理：pathlib 默认 UTF-8，可以显式指定
6. Python 的 async 文件 IO 要用 aiofiles（标准库 pathlib 是同步的）

和 Go/Java 对比：
- pathlib 面向对象写法比 os.path 优雅很多
- Python 是同步，但 FastAPI 用 async 会自动放在线程池
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="file-io-python", version="1.0.0")


class WriteRequest(BaseModel):
    path: str
    content: Any
    append: bool = False


@app.post("/file/write")
def write_file(req: WriteRequest) -> dict:
    """POST /file/write — 写文件（覆盖或追加）"""
    try:
        p = Path(req.path)
        # 确保父目录存在
        p.parent.mkdir(parents=True, exist_ok=True)

        # 把 content 转成字符串
        if isinstance(req.content, str):
            content = req.content
        else:
            content = json.dumps(req.content, ensure_ascii=False)

        if req.append:
            with open(p, "a", encoding="utf-8") as f:
                f.write(content)
        else:
            p.write_text(content, encoding="utf-8")

        return {
            "success": True,
            "path": req.path,
            "bytes_written": len(content.encode()),
            "append": req.append,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/file/read")
def read_file(path: str) -> dict:
    """GET /file/read — 读文件"""
    p = Path(path)
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"文件不存在: {path}")
    if not p.is_file():
        raise HTTPException(status_code=400, detail=f"不是文件: {path}")

    content = p.read_text(encoding="utf-8")
    return {
        "path": path,
        "content": content,
        "bytes": len(content.encode()),
    }


@app.get("/file/scan")
def scan_dir(dir: str, recursive: bool = True) -> dict:
    """GET /file/scan — 目录遍历"""
    start = Path(dir)
    if not start.exists():
        raise HTTPException(status_code=404, detail=f"目录不存在: {dir}")
    if not start.is_dir():
        raise HTTPException(status_code=400, detail=f"不是目录: {dir}")

    file_count = 0
    total_bytes = 0

    iterator = start.rglob("*") if recursive else start.iterdir()

    for p in iterator:
        try:
            if p.is_file():
                file_count += 1
                total_bytes += p.stat().st_size
        except PermissionError:
            pass  # 忽略权限错误

    return {
        "dir": dir,
        "recursive": recursive,
        "files": file_count,
        "total_bytes": total_bytes,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8097)
