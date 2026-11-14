"""
场景 09：HTTP 客户端（超时 / 重试 / 熔断） — Python 实现

Python HTTP Client 特点：
1. httpx（比 requests 好，支持 async + 连接池 + 超时粒度）
2. 重试：手动循环 + tenacity.wait_exponential 生成退避（retry_times 来自请求体，逐请求可变）
3. 熔断：pybreaker.CircuitBreaker — fail_max=3, reset_timeout=10
4. Mock Server：httpx.MockTransport 单例（无需启线程跑 http.server）
5. httpx.Timeout(connect=3.0, read=10.0, write=10.0) 分开配置

和 Java/Go 对比：
- httpx 原生 async（httpx.AsyncClient），比 requests 强
- Python 全局 GIL 不阻塞 IO 密集（httpx 用纯 Python 实现异步）
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Optional

import httpx
import pybreaker
from fastapi import FastAPI
from pydantic import BaseModel
from tenacity import wait as tenacity_wait

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

app = FastAPI(title="http-client-python", version="1.0.0")

MOCK_PORT = 8202
MOCK_BASE_URL = f"http://mockserver:8202"


# ==================== 内置 Mock Server（httpx.MockTransport 单例） ====================

def _make_mock_transport() -> httpx.MockTransport:
    """构造 httpx.MockTransport，作为 httpx.AsyncClient 的 transport 注入。

    替代原来的 threading.Thread + ThreadingHTTPServer：
    - 不启端口、不占线程，完全在内存里路由
    - handler 同步函数由 httpx 放到线程池执行，/slow 的 time.sleep(2) 不阻塞事件循环
    """

    def _handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/ok":
            return httpx.Response(200, json={"ok": True, "service": "py-mock"})
        elif request.url.path == "/slow":
            time.sleep(2)  # 模拟慢响应
            return httpx.Response(200, json={"ok": True, "slow": True})
        elif request.url.path == "/fail":
            return httpx.Response(500, json={"error": "mock failure"})
        else:
            return httpx.Response(404, json={"error": "not found"})

    return httpx.MockTransport(_handler)


_mock_transport = _make_mock_transport()


# ==================== 熔断器（pybreaker） ====================

# pybreaker.CircuitBreaker：fail_max 次失败后进入 open，reset_timeout 秒后半开
cb = pybreaker.CircuitBreaker(fail_max=3, reset_timeout=10)


# ==================== 请求模型 ====================

class CallReq(BaseModel):
    url: str = f"{MOCK_BASE_URL}/ok"
    timeout_ms: int = 5000
    retry_times: int = 2  # 总尝试次数 = retry_times + 1


# ==================== HTTP Client 核心 ====================

@app.post("/call-external")
async def call_external(req: CallReq):
    # 熔断检查（pybreaker 不允许时直接抛 CircuitBreakerError，这里手动检查状态）
    if cb.current_state == pybreaker.CircuitBreakerState.OPEN:
        logger.warning("circuit open, rejecting request", url=req.url)
        return {
            "success": False,
            "error": "CIRCUIT_OPEN: 熔断中",
            "status_code": 0,
            "latency_ms": 0,
            "retries": 0,
            "url": req.url,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    # 超时配置（分开：连接 3s / 读取 10s / 整体 timeout_ms）
    client_timeout = httpx.Timeout(
        connect=3.0,
        read=min(req.timeout_ms / 1000, 10.0),
        write=10.0,
        pool=5.0,
    )

    # MockTransport 注入：所有请求在内存里路由，不占端口
    transport = _mock_transport

    start = time.time()
    max_attempts = req.retry_times + 1
    last_error = None
    last_status = 0  # 最后一次尝试拿到的 HTTP 状态码（网络错误时为 0）

    async with httpx.AsyncClient(timeout=client_timeout, transport=transport) as client:
        for attempt in range(max_attempts):
            if attempt > 0:
                # tenacity.wait_exponential 生成退避：0.1s → 0.2s → 0.4s
                backoff = tenacity_wait.wait_exponential(multiplier=0.1)(attempt)
                logger.info("retry backoff", attempt=attempt, backoff_s=backoff)
                await asyncio.sleep(backoff)

            try:
                logger.info("http request", url=req.url, attempt=attempt + 1)
                resp = await client.get(req.url)
                last_status = resp.status_code

                # 5xx 重试
                if resp.status_code >= 500:
                    last_error = f"HTTP {resp.status_code}"
                    if attempt < req.retry_times:
                        continue
                    break  # 最后一次也失败 → 统一失败路径

                latency = int((time.time() - start) * 1000)
                cb.success()  # pybreaker 记录成功

                body_preview = None
                try:
                    body_preview = resp.json()
                except Exception:
                    body_preview = resp.text[:200]

                logger.info("http request success", url=req.url, status=resp.status_code,
                            latency_ms=latency, attempt=attempt)

                return {
                    "status_code": resp.status_code,
                    "latency_ms": latency,
                    "retries": attempt,
                    "success": True,
                    "body_preview": body_preview,
                    "url": req.url,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }

            except httpx.TimeoutException as e:
                last_error = f"TIMEOUT: {type(e).__name__}"
                last_status = 0
                if attempt < req.retry_times:
                    continue
            except httpx.RequestError as e:
                last_error = f"REQUEST_ERROR: {type(e).__name__}: {e}"
                last_status = 0
                if attempt < req.retry_times:
                    continue

    # 全部失败（网络错误或最后一次 5xx）
    cb.failure()  # pybreaker 记录失败
    logger.error("http request failed after retries", url=req.url, error=last_error,
                 last_status=last_status, retries=req.retry_times)
    return {
        "success": False,
        "status_code": last_status,
        "latency_ms": int((time.time() - start) * 1000),
        "retries": req.retry_times,
        "error": str(last_error),
        "url": req.url,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


@app.get("/health")
def health():
    return {
        "service": "http-client-python",
        "mock_port": MOCK_PORT,
        "cb_state": cb.current_state.name,
    }


if __name__ == "__main__":
    import uvicorn

    logger.info("service starting", port=8117, title="http-client-python")
    uvicorn.run(app, host="0.0.0.0", port=8117, log_level="debug")
