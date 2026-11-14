"""
场景 10：单机内存限流 — Python 实现（FastAPI + slowapi）

Python 限流特点：
1. slowapi 基于 limits 库，支持滑动窗口/固定窗口限流
2. asyncio 单线程事件循环 → 限流计数天然无并发竞争
3. slowapi 通过 @limiter.limit 装饰器声明限流规则
4. 自定义 429 响应，附带 total/allowed/rejected 统计

并发安全：Python asyncio 事件循环是单线程的，所以
异步函数内的所有操作天然串行，不需要加锁
"""
from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

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

app = FastAPI(title="rate-limit-python", version="1.0.0")


# ============ slowapi 限流器初始化 ============

# Limiter：key_func 用客户端 IP，default_limits 作为全局默认
limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def _custom_rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """自定义 429 响应，携带 total/allowed/rejected 统计"""
    retry_after = getattr(exc, "retry_after", None) or 1
    return JSONResponse(
        status_code=429,
        headers={"Retry-After": str(int(retry_after))},
        content={
            "error": "rate limit exceeded",
            "retry_after_s": int(retry_after),
            "limit": str(getattr(exc, "limit", "")),
            "total": _STATS["total"],
            "allowed": _STATS["allowed"],
            "rejected": _STATS["rejected"],
        },
    )


# ============ 运行时统计（slowapi 不提供，手动维护）============

_STATS = {"total": 0, "allowed": 0, "rejected": 0}


@app.middleware("http")
async def _count_requests(request: Request, call_next):
    """中间件：统计所有请求的 total/allowed/rejected，与原 TokenBucket 口径对齐"""
    _STATS["total"] += 1
    response = await call_next(request)
    if response.status_code == 429:
        _STATS["rejected"] += 1
    else:
        _STATS["allowed"] += 1
    return response


# ============ 端点 ============

@app.get("/api/heavy")
@limiter.limit("1/second")  # 每秒最多 1 个请求（滑动窗口，允许短时间突发）
async def heavy(request: Request):
    return {
        "ok": True,
        "endpoint": "/api/heavy",
        "total": _STATS["total"],
        "allowed": _STATS["allowed"],
        "rejected": _STATS["rejected"],
    }


@app.get("/health")
def health():
    return {
        "service": "rate-limit-python",
        "algorithm": "slowapi (sliding window, asyncio single-thread)",
        "default_limits": "60/minute",
        "endpoint_limits": "/api/heavy: 1/second",
        "total": _STATS["total"],
        "allowed": _STATS["allowed"],
        "rejected": _STATS["rejected"],
    }


if __name__ == "__main__":
    import uvicorn

    logger.info("service starting", port=8122, title="rate-limit-python")
    uvicorn.run(app, host="0.0.0.0", port=8122, log_level="debug")
