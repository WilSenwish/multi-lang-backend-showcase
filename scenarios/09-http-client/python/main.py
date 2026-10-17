"""
场景 09：HTTP 客户端（超时 / 重试 / 熔断） — Python 实现

Python HTTP Client 特点：
1. httpx（比 requests 好，支持 async + 连接池 + 超时粒度）
2. 重试：**手动指数退避循环** —— 因为重试次数来自请求体 retry_times（逐请求可变），
   tenacity 的 stop 条件也可以动态化，但装饰器写法在"读响应体后再决定是否重试"
   （5xx 也要消费 body）时不如裸循环直观；requirements 里的 tenacity 仅作备选
3. httpx.Client 默认连接池，max_keepalive_connections 配置
4. httpx.Timeout(connect=3.0, read=10.0, write=10.0) 分开配置
5. 熔断：手动实现（阈值 3 次连续失败 → open，10s 后半开）

和 Java/Go 对比：
- httpx 原生 async（httpx.AsyncClient），比 requests 强
- Python 全局 GIL 不阻塞 IO 密集（httpx 用纯 Python 实现异步）
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
import math
from http.server import HTTPServer, BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional, Callable

import httpx
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="http-client-python", version="1.0.0")


MOCK_PORT = 8202


# ==================== 内置 Mock Server ====================

def _run_mock_server():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # 抑制默认日志
            pass

        def _send(self, code: int, body: str):
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body.encode())

        def do_GET(self):
            if self.path == "/ok":
                self._send(200, '{"ok":true,"service":"py-mock"}')
            elif self.path == "/slow":
                time.sleep(2)
                self._send(200, '{"ok":true,"slow":true}')
            elif self.path == "/fail":
                self._send(500, '{"error":"mock failure"}')
            else:
                self._send(404, '{"error":"not found"}')

    # ThreadingHTTPServer：/slow 的 2s 睡眠发生在服务端线程里，
    # 单线程版会让后续请求排在睡眠后面（超时只中断了客户端，服务端仍在睡），
    # 把毫不相关的请求延迟放大到 2s —— 契约的耗时下界会被这种串扰污染。
    server = ThreadingHTTPServer(("127.0.0.1", MOCK_PORT), Handler)
    print(f"[Python MockServer] starting on http://localhost:{MOCK_PORT}")
    server.serve_forever()


threading.Thread(target=_run_mock_server, daemon=True).start()


# ==================== 熔断（手动实现） ====================

class CircuitBreaker:
    def __init__(self, threshold: int = 3, half_open_after: float = 10.0):
        self.threshold = threshold
        self.half_open_after = half_open_after
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._state = "closed"

    def allow(self) -> bool:
        if self._state == "open":
            if time.time() - self._last_failure_time >= self.half_open_after:
                self._state = "half-open"
                return True
            return False
        return True  # closed 或 half-open 都放行

    def record_success(self):
        self._failure_count = 0
        self._state = "closed"

    def record_failure(self):
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._failure_count >= self.threshold:
            self._state = "open"

    @property
    def state(self) -> str:
        return self._state


cb = CircuitBreaker(3, 10.0)


# ==================== 请求模型 ====================

class CallReq(BaseModel):
    url: str = f"http://localhost:{MOCK_PORT}/ok"
    timeout_ms: int = 5000
    retry_times: int = 2  # 总尝试次数 = retry_times + 1


# ==================== HTTP Client 核心 ====================

@app.post("/call-external")
async def call_external(req: CallReq):
    import asyncio

    # 熔断检查（响应键集合与"重试耗尽"分支保持一致，见模块底部说明）
    if not cb.allow():
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

    # 连接池配置
    transport = httpx.AsyncHTTPTransport(
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
    )

    start = time.time()
    max_attempts = req.retry_times + 1
    last_error = None
    last_status = 0  # 最后一次尝试拿到的 HTTP 状态码（网络错误时为 0）

    async with httpx.AsyncClient(timeout=client_timeout, transport=transport) as client:
        for attempt in range(max_attempts):
            if attempt > 0:
                backoff = (2 ** (attempt - 1)) * 100 / 1000  # 0.1 → 0.2 → 0.4s
                await asyncio.sleep(backoff)

            try:
                print(f"[HTTP-CLIENT] → GET {req.url} (attempt {attempt + 1})")
                resp = await client.get(req.url)
                last_status = resp.status_code

                # 5xx 重试
                if resp.status_code >= 500:
                    last_error = f"HTTP {resp.status_code}"
                    if attempt < req.retry_times:
                        continue
                    break  # 最后一次也失败 → 统一失败路径

                latency = int((time.time() - start) * 1000)
                cb.record_success()

                body_preview = None
                try:
                    body_preview = resp.json()
                except Exception:
                    body_preview = resp.text[:200]

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

    # 全部失败（网络错误或最后一次 5xx）—— 5xx 时 status_code 必须是真实状态码（README 统一接口）
    cb.record_failure()
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
        "cb_state": cb.state,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8117, log_level="warning")
