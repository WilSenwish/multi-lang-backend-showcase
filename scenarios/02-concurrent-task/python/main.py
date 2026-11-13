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
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI(title="concurrent-task-python", version="1.0.0")


# 统一契约：FastAPI 默认把请求体解析/校验失败返回 422，与其余四门的 400 不一致。
# 这里显式改写成 400（契约：非法入参一律 400）。
@app.exception_handler(RequestValidationError)
async def _validation_to_400(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=400, content={"error": "invalid request"})


class RunRequest(BaseModel):
    # 字段缺省走默认值 100/100/10；显式传非法值由 run() 统一返回 400
    # （不用 Field(ge=...)：pydantic 的校验错误是 422，与其余四门的 400 不一致）
    task_count: int = 500
    task_delay_ms: int = 100
    concurrency: int = 10


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
    # 统一契约：显式传入的非法值一律 400（与 Go/Java/Rust/TS 对齐）
    if req.task_count < 1:
        raise HTTPException(status_code=400, detail="task_count must be >= 1")
    if req.task_delay_ms < 0:
        raise HTTPException(status_code=400, detail="task_delay_ms must be >= 0")
    if req.concurrency < 1:
        raise HTTPException(status_code=400, detail="concurrency must be >= 1")

    # 边界保护：并发数不超过任务数
    concurrency = min(req.concurrency, req.task_count)

    start = time.perf_counter()

    # ========== Python asyncio 并发核心 ==========
    # asyncio.Semaphore(concurrency) = 同时最多 concurrency 个协程在执行
    semaphore = asyncio.Semaphore(concurrency)

    # 创建所有任务协程（此时还没执行，只是创建）[生成式]
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


from typing import Annotated
from fastapi import Query

@app.get("/get_run", response_model=RunResponse)
async def get_run(params: Annotated[RunRequest, Query()]):
    return await run(params)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8087)
