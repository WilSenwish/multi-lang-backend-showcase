"""场景 16：大文件流式处理 —— Python 用原始 fd + 固定大小缓冲。

语义契约（五门语言必须逐字一致，见场景 README）：
  1. 生成一个确定性的定长行文件（每行 10 字节：NNN,AAAAA\\n），生成过程本身也是流式的
  2. 以 chunk_kib × 1024 字节的固定缓冲读取，**绝不整体读入内存**
  3. 行可能跨越 chunk 边界 → 用"残余行拼接"处理，不能假设 chunk 边界 = 行边界
  4. 逐行解析 amount，过滤 amount >= min_amount，输出 NNN,BBBBBB\\n（11 字节），流式写
  5. 输入/输出各算一份 SHA-256（取前 8 字节 hex），处理完删除两个临时文件

Python 的取舍：
  - 标准库的 IO 默认是"行迭代 / 一次 read()"，两者都很容易滑向"整体读入"；
    要做到真正的固定内存，必须退回 os.open/os.read 这一层自己管缓冲
  - resource.getrusage 给出 ru_maxrss（进程级峰值），是这里唯一廉价的观测手段；
    tracemalloc 能给出精确的堆分配，但开销是数量级的，生产里不能常开
  - 代价：解释器的每行开销被放大 —— 同样的数据量，Python 的墙钟时间最长（见 README 实测）
"""

import hashlib
import os
import resource
import sys
import tempfile
import time
from typing import Optional

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="large-file-streaming (python)")

PORT = 8152
# 确定性数据序列：h(i) = (i+1)*MULT + INC（mod 2^64），amount = (h >> 32) % 100000
MULT = 6364136223846793005
INC = 1442695040888963407
MASK = (1 << 64) - 1
LINE_IN = 10    # "%03d,%05d\n"
LINE_OUT = 11   # "%03d,%06d\n"
GEN_BUF = 64 * 1024

# 预生成的查表：把"每行格式化"的开销从 3 次 % 运算降到 2 次查表 + 拼接。
# 在模块加载期构建（早于任何请求），因此不会污染处理阶段的 RSS 基线。
_PREFIX = [b"%03d," % g for g in range(1000)]          # 行首 "NNN," 只有 1000 种
_AMOUNT = [b"%05d" % a for a in range(100000)]         # amount 只有 100000 种

_IS_DARWIN = sys.platform == "darwin"


class StreamRequest(BaseModel):
    size_mb: Optional[int] = 32
    chunk_kib: Optional[int] = 64
    min_amount: Optional[int] = 50000


class StreamResponse(BaseModel):
    lang: str
    size_mb: int
    chunk_kib: int
    min_amount: int
    bytes_read: int
    lines_read: int
    bytes_written: int
    lines_written: int
    output_file_bytes: int
    checksum: str
    output_checksum: str
    chunks: int
    gen_ms: int
    proc_ms: int
    elapsed_ms: int
    throughput_mb_s: float
    rss_before_bytes: int
    rss_peak_bytes: int
    rss_delta_bytes: int
    peak_heap_bytes: int
    heap_metric: str
    cleanup: bool


def rss_bytes() -> int:
    """进程 RSS 峰值（ru_maxrss）。单位：Linux 为 KB，macOS 为 bytes。"""
    v = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(v if _IS_DARWIN else v * 1024)


def _write_all(fd: int, data) -> None:
    """os.write 不保证一次写完（对普通文件通常写完，但语义上不保证）——必须循环。"""
    mv = memoryview(data)
    while mv:
        n = os.write(fd, mv)
        mv = mv[n:]


def generate(path: str, lines: int) -> None:
    """阶段一：流式生成源文件（固定缓冲 64KiB，绝不整体拼进内存）。"""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        buf = bytearray()
        h = INC
        append = buf.append
        for i in range(lines):
            h = (h + MULT) & MASK
            amount = (h >> 32) % 100000
            buf += _PREFIX[i % 1000]
            buf += _AMOUNT[amount]
            append(10)
            if len(buf) + LINE_IN > GEN_BUF:
                _write_all(fd, buf)
                buf.clear()
        if buf:
            _write_all(fd, buf)
    finally:
        os.close(fd)


def process(src: str, dst: str, chunk: int, min_amount: int) -> dict:
    """阶段二：读 → 解析 → 过滤 → 转换 → 写。全程只持有固定大小的缓冲。"""
    h_in = hashlib.sha256()
    h_out = hashlib.sha256()
    fd_in = os.open(src, os.O_RDONLY)
    fd_out = os.open(dst, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)

    buf = bytearray(chunk)
    mv = memoryview(buf)
    pending = bytearray()          # 上一个 chunk 剩下的半行
    out_buf = bytearray()

    chunks = 0
    bytes_read = 0
    lines_read = 0
    bytes_written = 0
    lines_written = 0
    t0 = time.time()

    try:
        while True:
            filled = 0
            while filled < chunk:
                block = os.read(fd_in, chunk - filled)
                if not block:
                    break
                mv[filled:filled + len(block)] = block
                filled += len(block)
            if filled == 0:
                break
            chunks += 1
            bytes_read += filled
            h_in.update(mv[:filled])

            pending += mv[:filled]
            start = 0
            nl = pending.find(b"\n", start)
            while nl != -1:
                lines_read += 1
                if nl - start >= LINE_IN - 1:
                    # 直接从字节解析 amount（offset 4..8）：不切片、不 int(bytes)、不 split
                    amount = ((pending[start + 4] - 48) * 10000
                              + (pending[start + 5] - 48) * 1000
                              + (pending[start + 6] - 48) * 100
                              + (pending[start + 7] - 48) * 10
                              + (pending[start + 8] - 48))
                    if amount >= min_amount:
                        out_buf += pending[start:start + 4]      # "NNN," 原样拷贝
                        out_buf += b"%06d" % (amount * 2)
                        out_buf += b"\n"
                        lines_written += 1
                        bytes_written += LINE_OUT
                        if len(out_buf) + LINE_OUT > chunk:
                            h_out.update(out_buf)
                            _write_all(fd_out, out_buf)
                            out_buf.clear()
                start = nl + 1
                nl = pending.find(b"\n", start)
            if start:
                del pending[:start]
            if filled < chunk:      # 没读满 = EOF
                break
        if out_buf:
            h_out.update(out_buf)
            _write_all(fd_out, out_buf)
    finally:
        os.close(fd_in)
        os.close(fd_out)

    secs = time.time() - t0
    return {
        "bytes_read": bytes_read,
        "lines_read": lines_read,
        "bytes_written": bytes_written,
        "lines_written": lines_written,
        "checksum": h_in.hexdigest()[:16],
        "output_checksum": h_out.hexdigest()[:16],
        "chunks": chunks,
        "proc_ms": int(secs * 1000),
        "throughput_mb_s": (bytes_read / (1024 * 1024) / secs) if secs > 0 else 0.0,
    }


@app.post("/stream/process")
def stream_process(req: StreamRequest):
    size_mb = max(1, min(512, req.size_mb or 32))
    chunk_kib = max(1, min(4096, req.chunk_kib or 64))
    min_amount = max(0, min(99999, req.min_amount or 50000))

    lines = size_mb * 1024 * 1024 // LINE_IN
    tag = "stream16-%d-%d" % (os.getpid(), time.time_ns())
    src = os.path.join(tempfile.gettempdir(), tag + ".in")
    dst = os.path.join(tempfile.gettempdir(), tag + ".out")

    rss_before = rss_bytes()
    t_all = time.time()

    generate(src, lines)
    gen_ms = int((time.time() - t_all) * 1000)

    res = process(src, dst, chunk_kib * 1024, min_amount)

    # 真实写出的字节数（stat 文件，而不是信任计数器）—— 计数器可能与真实写入脱节
    output_file_bytes = os.path.getsize(dst)

    # 清理临时文件：不删的话多跑几次就把磁盘撑满了
    existed = os.path.exists(src)
    for p in (src, dst):
        try:
            os.remove(p)
        except FileNotFoundError:
            pass
    cleanup = existed and not os.path.exists(src) and not os.path.exists(dst)

    rss_peak = rss_bytes()
    return StreamResponse(
        lang="python",
        size_mb=size_mb,
        chunk_kib=chunk_kib,
        min_amount=min_amount,
        output_file_bytes=output_file_bytes,
        gen_ms=gen_ms,
        elapsed_ms=int((time.time() - t_all) * 1000),
        rss_before_bytes=rss_before,
        rss_peak_bytes=rss_peak,
        rss_delta_bytes=rss_peak - rss_before,
        # Python 没有廉价的"堆字节数"口径：tracemalloc 精确但开销数量级，
        # 因此这里如实回传 RSS 同口径值，并在 heap_metric 里写明。
        peak_heap_bytes=rss_peak,
        heap_metric="python.resource.ru_maxrss（与 RSS 同口径；无廉价堆字节计数）",
        cleanup=cleanup,
        **res,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
