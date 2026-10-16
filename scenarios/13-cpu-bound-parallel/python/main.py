"""
场景 13：CPU 密集并行计算 — Python 实现（FastAPI + multiprocessing）

统一 API 契约：
    POST /compute
    {"task_count":8,"iterations":2000000,"concurrency":4}
    → {"total_tasks":8,"iterations":2000000,"concurrency":4,"cpu_cores":10,
       "total_time_ms":1234,"checksum":"<uint64 无符号十进制>",
       "results":[{"id":0,"checksum":"<uint64>","duration_ms":150}, ...]}

为什么这个场景对 Python 是"现原形"的时刻
----------------------------------------
场景 02 的任务是 `await asyncio.sleep()`，瓶颈在等待，GIL 会在 IO 期间释放，
所以 asyncio 表现不差。但本场景的任务是**纯计算**，情况完全不同：

1. **GIL（全局解释器锁）保证任意时刻只有一个线程执行 Python 字节码。**
   因此 `ThreadPoolExecutor` / `asyncio` 在 CPU 密集任务上**完全没有并行效果** ——
   4 个线程跑 4 个计算任务，总耗时和串行几乎一样（甚至因为切换开销更慢）。

2. **唯一的出路是换进程：`multiprocessing` / `ProcessPoolExecutor`。**
   每个进程有独立的解释器和独立的 GIL，才能真正铺满多核。

3. **代价（这才是选型时真正要算的账）：**
   - 进程启动成本：macOS 默认 `spawn` 启动方式，每个子进程都要重新 import 一遍模块；
   - 数据只能靠 pickle 序列化跨进程传递，无法共享内存中的对象（大对象会非常痛）；
   - 每个进程有独立内存，N 个进程 = N 份解释器内存。

4. **整数语义差异：** Python 的 int 是任意精度，不像 Java/Go/Rust 那样自然环绕。
   为了和其余四门语言逐位对齐，这里必须**每步手动 `& MASK`** 截断到 64 位 ——
   这个额外的 & 运算本身也是性能开销的一部分。

对比结论：Python 的并发模型天然为 IO 密集设计；CPU 密集场景下，
"用 Python" 这个决定意味着要么接受单核性能，要么接受多进程的工程复杂度。
"""

from __future__ import annotations

import os
import time
from concurrent.futures import ProcessPoolExecutor

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="cpu-bound-parallel-python", version="1.0.0")

# MMIX 线性同余发生器常数：state = state * MULT + INC (mod 2^64)
MULT = 6364136223846793005
INC = 1442695040888963407
MASK = (1 << 64) - 1

DEFAULT_TASK_COUNT = 8
DEFAULT_ITERATIONS = 2_000_000
DEFAULT_CONCURRENCY = 4


class ComputeRequest(BaseModel):
    """计算请求（字段可省略，省略时走缺省值）"""

    task_count: int = Field(default=DEFAULT_TASK_COUNT, ge=1)
    iterations: int = Field(default=DEFAULT_ITERATIONS, ge=1)
    concurrency: int = Field(default=DEFAULT_CONCURRENCY, ge=1)


class TaskResult(BaseModel):
    """单任务结果（checksum 必须与其余四门语言逐位一致）"""

    id: int
    checksum: str
    duration_ms: int


class ComputeResponse(BaseModel):
    """计算响应"""

    total_tasks: int
    iterations: int
    concurrency: int
    cpu_cores: int
    total_time_ms: int
    checksum: str
    results: list[TaskResult]


def compute_state(task_id: int, iterations: int) -> int:
    """跑 iterations 次 LCG 迭代，每步截断到 uint64。

    必须显式 & MASK：Python 的 int 是任意精度，不截断的话结果会与
    Java/Go/Rust/TS 的无符号 64 位环绕**完全不同**。
    """
    state = (task_id + 1) & MASK
    for _ in range(iterations):
        state = (state * MULT + INC) & MASK
    return state


def _run_task(task_id: int, iterations: int) -> tuple[int, int, int]:
    """在子进程中执行单个任务。

    必须是模块级函数（可被 pickle），否则 spawn 模式下无法传给子进程。
    """
    t0 = time.perf_counter()
    state = compute_state(task_id, iterations)
    duration_ms = int((time.perf_counter() - t0) * 1000)
    return task_id, state, duration_ms


@app.post("/compute", response_model=ComputeResponse)
def compute(req: ComputeRequest | None = None):
    """执行 CPU 密集的并行计算。

    用 `def` 而不是 `async def`：任务是阻塞式的，FastAPI 会把同步端点放进线程池，
    不会卡住事件循环；若写成 async def 再调 f.result()，事件循环会被直接阻塞。
    """
    req = req or ComputeRequest()
    task_count = max(1, req.task_count)
    iterations = max(1, req.iterations)
    concurrency = min(max(1, req.concurrency), task_count)

    start = time.perf_counter()

    # ⭐ 关键：CPU 密集必须用 ProcessPoolExecutor（多进程），
    #    换 ThreadPoolExecutor 或 asyncio 都会因 GIL 退化成串行。
    with ProcessPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(_run_task, i, iterations) for i in range(task_count)]
        # 按提交顺序收集，保证 results 按 id 升序
        collected = [f.result() for f in futures]

    results = [
        TaskResult(id=tid, checksum=str(state), duration_ms=dur)
        for tid, state, dur in collected
    ]

    # 累加和取 uint64 环绕（加法模 2^64 满足交换律，与执行顺序无关）
    checksum = sum(r[1] for r in collected) & MASK

    elapsed_ms = int((time.perf_counter() - start) * 1000)

    return ComputeResponse(
        total_tasks=task_count,
        iterations=iterations,
        concurrency=concurrency,
        cpu_cores=os.cpu_count() or 1,
        total_time_ms=elapsed_ms,
        checksum=str(checksum),
        results=results,
    )


@app.get("/health")
def health():
    """健康检查"""
    return {"service": "cpu-bound-parallel-python", "cpu_cores": os.cpu_count() or 1}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8137, log_level="warning")
