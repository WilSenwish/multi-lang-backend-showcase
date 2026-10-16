"""
场景 10：单机内存限流 — Python 实现（FastAPI + 手写令牌桶）

Python 限流特点：
1. asyncio 单线程事件循环 → 天然无并发竞争（不需要锁！）
2. 用 time.monotonic() 计算令牌填充
3. 手写令牌桶比 aiometer / tenacity 更可控
4. GIL 保证多线程安全（但 Python 主要用 asyncio）

并发安全：Python asyncio 事件循环是单线程的，所以
异步函数内的所有操作天然串行，不需要加锁
"""
from __future__ import annotations

import asyncio
import time
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

app = FastAPI(title="rate-limit-python", version="1.0.0")


# ============ 令牌桶（asyncio 单线程，无锁） ============

class TokenBucket:
    """
    令牌桶限流器 — 手写实现
    单线程事件循环内使用，不需要任何锁！

    参数：
    - qps: 每秒填充令牌数（rate）
    - burst: 桶容量（最多允许连续的突发请求数）
    """

    def __init__(self, qps: float, burst: int):
        self.qps = qps
        self.burst = burst
        self.tokens = float(burst)  # 初始装满
        self.last_refill = time.monotonic()
        self.total = 0
        self.allowed = 0
        self.rejected = 0

    def _refill(self):
        """根据经过的时间填充令牌"""
        now = time.monotonic()
        elapsed = now - self.last_refill
        refill = elapsed * self.qps
        self.tokens = min(self.burst, self.tokens + refill)
        self.last_refill = now

    def try_acquire(self) -> bool:
        """尝试获取 1 个令牌"""
        self._refill()
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            self.total += 1
            self.allowed += 1
            return True
        self.total += 1
        self.rejected += 1
        return False

    def retry_after_ms(self) -> int:
        """计算下一个令牌的等待时间（毫秒）"""
        self._refill()
        deficit = 1.0 - self.tokens
        if deficit <= 0:
            return 0
        return int(deficit / self.qps * 1000)


# 单例（asyncio 单线程天然安全）
limiter = TokenBucket(qps=1.0, burst=10)


# ============ 端点 ============

@app.get("/api/heavy")
async def heavy():
    if not limiter.try_acquire():
        retry_ms = limiter.retry_after_ms()
        return JSONResponse(
            status_code=429,
            headers={"Retry-After": str(max(1, retry_ms // 1000 + 1))},
            content={
                "error": "rate limit exceeded",
                "retry_after_ms": retry_ms,
                "total": limiter.total,
                "allowed": limiter.allowed,
                "rejected": limiter.rejected,
            },
        )

    return {
        "ok": True,
        "endpoint": "/api/heavy",
        "total": limiter.total,
        "allowed": limiter.allowed,
        "rejected": limiter.rejected,
    }


@app.get("/health")
def health():
    return {
        "service": "rate-limit-python",
        "algorithm": "token-bucket (asyncio single-thread, no lock)",
        "qps": limiter.qps,
        "burst": limiter.burst,
        "total": limiter.total,
        "allowed": limiter.allowed,
        "rejected": limiter.rejected,
    }


if __name__ == "__main__":
    import uvicorn
    print("限流配置：QPS=1, burst=10 (每秒 1 个令牌，桶容量 10)")
    print("Python asyncio 单线程事件循环 → 天然无并发竞争")
    uvicorn.run(app, host="0.0.0.0", port=8122, log_level="warning")
