"""场景 15：结构化并发 + 取消传播 —— Python 用 asyncio.TaskGroup + asyncio.timeout。

语义契约（五门语言必须逐字一致，见场景 README）：
  - 扇出 tasks 个子任务，id = 0..tasks-1，全部并发启动
  - id == fail_index 的子任务在 fail_after_ms 后"失败"；其余子任务跑满 task_ms 后"完成"
  - 任一子任务失败 / 父作用域超时 → 取消信号必须传播到所有兄弟任务（cancelled）
  - 作用域退出时所有子任务必须已结束（结构化保证），leaked 恒为 0

Python 的主场优势：TaskGroup 是语言级的结构化并发原语 ——
子任务失败会自动取消兄弟任务，async with 退出即代表所有子任务已收尾。
取消传播由 CancelledError 完成，等待必须用可中断的 asyncio.sleep。
"""

import asyncio
import time
from contextlib import suppress
from typing import List, Optional

from fastapi import FastAPI
from pydantic import BaseModel, Field

# ==================== structlog 结构化日志初始化 ====================
import logging
import sys

import structlog


def _configure_structlog() -> None:
    """配置 structlog：JSON 格式输出到 stdout，最低 DEBUG 级别"""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.ExceptionPrettyPrinter(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


_configure_structlog()
logger = structlog.get_logger()

app = FastAPI(title="structured-concurrency (python)")

# ---- 运行时统计（供 /stats 暴露，验证器用它做"取消是否真的生效"的延迟判定）----
STATS = {"active": 0, "started": 0, "completed": 0, "cancelled": 0, "failed": 0}


class FanoutRequest(BaseModel):
    tasks: int = 6
    task_ms: int = 300
    fail_index: int = -1
    fail_after_ms: int = 100
    timeout_ms: int = 0


class FanoutResponse(BaseModel):
    lang: str
    tasks: int
    task_ms: int
    fail_index: int
    fail_after_ms: int
    timeout_ms: int
    outcome: str                 # completed | failed | timeout
    completed: List[int] = Field(default_factory=list)
    cancelled: List[int] = Field(default_factory=list)
    failed: int = -1             # -1 表示无任务失败
    elapsed_ms: int
    leaked: int                  # 作用域退出时仍在运行的子任务数（结构化保证 = 0）


class StatsResponse(BaseModel):
    lang: str
    active_tasks: int
    started: int
    completed: int
    cancelled: int
    failed: int


def _validate(tasks: int, task_ms: int, fail_index: int, fail_after_ms: int, timeout_ms: int):
    if not 1 <= tasks <= 64:
        return "tasks must be in [1, 64]"
    if not 1 <= task_ms <= 10000:
        return "task_ms must be in [1, 10000]"
    if not -1 <= fail_index < tasks:
        return "fail_index must be in [-1, tasks)"
    if not 0 <= fail_after_ms <= 10000:
        return "fail_after_ms must be in [0, 10000]"
    if not 0 <= timeout_ms <= 10000:
        return "timeout_ms must be in [0, 10000]"
    return None


@app.get("/health")
async def health():
    return {"service": "structured-concurrency", "lang": "python", "engine": "asyncio.TaskGroup"}


@app.get("/stats")
async def stats():
    return StatsResponse(lang="python", active_tasks=STATS["active"], started=STATS["started"],
                         completed=STATS["completed"], cancelled=STATS["cancelled"],
                         failed=STATS["failed"])


@app.post("/fanout")
async def fanout(req: FanoutRequest):
    err = _validate(req.tasks, req.task_ms, req.fail_index, req.fail_after_ms, req.timeout_ms)
    if err:
        return {"error": err}

    tasks, fail_index = req.tasks, req.fail_index
    outcomes = ["pending"] * tasks
    t0 = time.time()

    async def worker(i: int):
        STATS["started"] += 1
        STATS["active"] += 1
        try:
            if i == fail_index:
                await asyncio.sleep(req.fail_after_ms / 1000.0)
                outcomes[i] = "failed"
                STATS["failed"] += 1
                raise RuntimeError(f"task {i} failed as requested")
            await asyncio.sleep(req.task_ms / 1000.0)
            outcomes[i] = "completed"
            STATS["completed"] += 1
        except asyncio.CancelledError:
            # 取消传播在这里落地：不吞掉，记录状态后继续抛出，交给 TaskGroup 收尾
            if outcomes[i] == "pending":
                outcomes[i] = "cancelled"
                STATS["cancelled"] += 1
            raise
        finally:
            STATS["active"] -= 1

    async def run_group():
        async with asyncio.TaskGroup() as tg:
            for i in range(tasks):
                tg.create_task(worker(i))

    if req.timeout_ms > 0:
        # asyncio.timeout：deadline 一到就取消作用域内全部子任务（超时即取消传播）
        with suppress(TimeoutError, asyncio.CancelledError):
            async with asyncio.timeout(req.timeout_ms / 1000.0):
                await run_group()
    else:
        # 子任务失败会被 TaskGroup 包装成 ExceptionGroup；失败即取消兄弟任务
        with suppress(ExceptionGroup):
            await run_group()

    elapsed_ms = int((time.time() - t0) * 1000)

    completed = sorted(i for i, o in enumerate(outcomes) if o == "completed")
    cancelled = sorted(i for i, o in enumerate(outcomes) if o == "cancelled")
    failed = next((i for i, o in enumerate(outcomes) if o == "failed"), -1)

    if failed >= 0:
        outcome = "failed"
    elif cancelled:
        outcome = "timeout"
    else:
        outcome = "completed"

    return FanoutResponse(
        lang="python", tasks=tasks, task_ms=req.task_ms, fail_index=fail_index,
        fail_after_ms=req.fail_after_ms, timeout_ms=req.timeout_ms,
        outcome=outcome, completed=completed, cancelled=cancelled, failed=failed,
        elapsed_ms=elapsed_ms, leaked=STATS["active"],
    )


if __name__ == "__main__":
    import uvicorn

    PORT = 8147
    logger.info("service starting", port=PORT, title="structured-concurrency")
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="debug")
