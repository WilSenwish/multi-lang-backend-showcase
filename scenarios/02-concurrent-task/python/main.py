"""
场景 02：并发任务处理 — Python 实现 (FastAPI + asyncio)

Python 并发模型特点：
1. **GIL（全局解释器锁）**：任意时刻只有一个线程执行 Python 字节码
2. asyncio 是**单线程事件循环**，协程本质上是协作式多任务
3. 但 IO 密集场景（如 sleep），GIL 会在 IO 等待时释放
4. 所以 asyncio + Semaphore 在 IO 密集任务上表现很好
5. **但 CPU 密集任务 asyncio 帮不了**，需要 multiprocessing

和 Java/Go/Rust 的本质区别：
- Java/Go/Rust 是多线程真并行（多核 CPU 都能利用）
- Python asyncio 是单线程假并行（只是调度更高效）
- 但 sleep 这种 IO 密集，asyncio 效率 ≈ 多线程

限流原语：asyncio.Semaphore(concurrency)
"""
from __future__ import annotations

import asyncio
import time
from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="concurrent-task-python", version="1.0.0")


class RunRequest(BaseModel):
    task_count: int = Field(default=100, ge=1)
    task_delay_ms: int = Field(default=100, ge=0)
    concurrency: int = Field(default=10, ge=1)


class TaskResult(BaseModel):
    id: int
    status: str
    duration_ms: int


class RunResponse(BaseModel):
    total_tasks: int
    concurrency: int
    total_time_ms: int
    throughput: float
    task_delay_ms: int
    results: list[TaskResult]


async def _execute_task(task_id: int, delay_ms: int, semaphore: asyncio.Semaphore) -> TaskResult:
    """
    单个异步任务。
    Semaphore 是 Python 的并发限流原语 —— acquire() 获得许可，release() 释放。
    同时最多 semaphore._value 个协程在执行。
    """
    async with semaphore:
        task_start = time.perf_counter()
        # asyncio.sleep 是非阻塞的 —— 事件循环在等待期间可以调度其他协程
        await asyncio.sleep(delay_ms / 1000.0)
        duration_ms = int((time.perf_counter() - task_start) * 1000)
        return TaskResult(id=task_id, status="ok", duration_ms=duration_ms)


@app.post("/run", response_model=RunResponse)
async def run(req: RunRequest) -> RunResponse:
    # 边界保护
    concurrency = min(req.concurrency, req.task_count)

    start = time.perf_counter()

    # ========== Python asyncio 并发核心 ==========
    # asyncio.Semaphore(concurrency) = 同时最多 concurrency 个协程在执行
    semaphore = asyncio.Semaphore(concurrency)

    # 创建所有任务协程（此时还没执行，只是创建）
    coroutines = [
        _execute_task(i, req.task_delay_ms, semaphore)
        for i in range(req.task_count)
    ]

    # asyncio.gather 并发执行所有协程，等待全部完成
    results: list[TaskResult] = await asyncio.gather(*coroutines)
    # ===========================================

    total_ms = int((time.perf_counter() - start) * 1000)
    throughput = round(req.task_count / (total_ms / 1000), 2) if total_ms > 0 else float(req.task_count)

    return RunResponse(
        total_tasks=req.task_count,
        concurrency=concurrency,
        total_time_ms=total_ms,
        throughput=throughput,
        task_delay_ms=req.task_delay_ms,
        results=results,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8087)
