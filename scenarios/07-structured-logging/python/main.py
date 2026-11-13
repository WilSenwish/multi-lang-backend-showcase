"""
场景 07：结构化日志 — Python 实现（structlog + FastAPI）

Python 结构化日志特点：
1. structlog 是 Python 生态结构化日志事实标准
2. 链式 API：structlog.get_logger().bind(**ctx).info("msg", key=value)
3. processor pipeline：每经过一个 processor 做一次变换（时间戳、级别、JSON 渲染）
4. 和标准 logging 兼容，也能独立用
5. 性能不如 Go/Rust，但比原生 logging 好

和 Java MDC / Go context 对比：
- Python 用 contextvars（Python 3.7+）做类似 MDC 的上下文传递
- structlog 的 processor 链非常灵活，可以插入自定义 processor
- 性能：纯 Python 比 zap/tracing/pino 慢 10-100x
"""
from __future__ import annotations

import contextvars
import logging
import sys
import time
import uuid
from typing import Optional

import structlog
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

app = FastAPI(title="structured-logging-python", version="1.0.0")


# ==================== structlog 配置 ====================

def setup_logging():
    """配置 structlog 输出 JSON 到 stdout"""
    # 输出重定向到文件时 stdout 默认块缓冲，日志会延迟整块出现；强制行缓冲
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass

    structlog.configure(
        processors=[
            # 0. 把 contextvars 里的链路字段（requestId/userId/path）合并进每条日志
            #    （这就是 Java MDC 的 Python 版对应物；少了这个 processor，
            #     bind_contextvars 存了值也不会出现在日志里）
            structlog.contextvars.merge_contextvars,
            # 1. 给所有事件加时间戳
            structlog.processors.TimeStamper(fmt="iso"),
            # 2. 加日志级别
            structlog.stdlib.add_log_level,
            # 3. 加 caller 信息（logger 名、函数、行号）
            structlog.processors.CallsiteParameterAdder([
                structlog.processors.CallsiteParameter.FILENAME,
                structlog.processors.CallsiteParameter.FUNC_NAME,
                structlog.processors.CallsiteParameter.LINENO,
            ]),
            # 4. 处理异常栈（exc_info=True 时渲染 traceback）
            structlog.processors.format_exc_info,
            # 5. 最后渲染成 JSON（ensure_ascii=False 支持中文）
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
        # 事件字典工厂（make_filtering_bound_logger 第一个参数是数值级别）
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.INFO,
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


setup_logging()
logger = structlog.get_logger()


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request, exc: RequestValidationError):
    """把 pydantic 的 422 统一改写为 400（与其余四门一致：非法入参一律 400）"""
    return JSONResponse(status_code=400, content={"error": "invalid parameters"})


# ==================== Request Context（类似 Java MDC / Go context） ====================

# Python contextvars：请求级别的上下文变量（类似 Java MDC）
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
user_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("user_id", default="anonymous")
path_var: contextvars.ContextVar[str] = contextvars.ContextVar("path", default="-")


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    """每个请求开始时设置 contextvars，后续日志自动带上"""
    req_id = uuid.uuid4().hex[:8]
    request_id_var.set(req_id)
    path_var.set(request.url.path)

    # 用 structlog 的 contextvars 把链路字段注入到每条日志（Java MDC 的对应物）
    bound_logger = logger.bind(
        requestId=req_id,
        userId=user_id_var.get(),
        path=request.url.path,
    )
    structlog.contextvars.bind_contextvars(
        requestId=req_id,
        userId=user_id_var.get(),
        path=request.url.path,
    )

    start = time.time()
    try:
        response = await call_next(request)
        return response
    finally:
        structlog.contextvars.clear_contextvars()
        cost_ms = int((time.time() - start) * 1000)
        bound_logger.info("request completed", costMs=cost_ms)


# ==================== 端点 ====================

@app.get("/ping")
async def ping():
    logger.info("ping request handled")
    return {"pong": True, "request_id": request_id_var.get()}


@app.get("/debug")
async def debug():
    # Debug 级别：min_level=INFO 默认不开，实际会被过滤
    logger.debug("debug request received", param1="value1", param2=42)
    # 该端点的日志 userId 与其余四门一致为 debug-user（中间件默认值是 anonymous）
    structlog.contextvars.bind_contextvars(userId="debug-user")
    logger.info("debug endpoint hit")
    return {"debug": True, "request_id": request_id_var.get()}


@app.get("/error")
async def error_endpoint():
    try:
        null_str: Optional[str] = None
        null_str.split(",")  # AttributeError!
    except Exception as e:
        structlog.contextvars.bind_contextvars(userId="error-user")
        # 带 exc_info=True 会自动在 JSON 里加 exc_info 字段（格式化的 traceback）
        logger.error(
            "request failed with exception",
            costMs=150,
            errorCode="NULL_POINTER",
            exc_info=True,
        )
    return {"error": "simulated"}


@app.get("/bench")
async def bench(count: int = Query(default=1000)):
    # count 必须 >= 1（与其余四门一致：0/负数/非数字都是客户端错误 → 400）
    if count < 1:
        raise HTTPException(status_code=400, detail="count must be >= 1")
    structlog.contextvars.bind_contextvars(userId="bench-user")
    start = time.time()
    for i in range(count):
        logger.info("benchmark log entry", index=i, total=count)
    cost = time.time() - start
    avg_ns = int(cost * 1_000_000_000 / count)

    logger.info("benchmark completed", count=count, totalCostMs=int(cost * 1000), avgLogNs=avg_ns)

    return {
        "count": count,
        "total_cost_ms": int(cost * 1000),
        "avg_log_ns": avg_ns,
        "request_id": request_id_var.get(),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8107, log_level="debug")
