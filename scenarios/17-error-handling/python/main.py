"""场景 17：错误处理深水区 —— Python 版本。

语义契约（五门语言必须逐字一致，见场景 README）：
  GET /errors/{kind} —— 五种"错误形态"，每一种都必须落成同一个结构化响应体：
    - not_found      → 404 NOT_FOUND          cause_chain = ["user 42 not found"]
    - validation     → 400 VALIDATION_FAILED  details = ["email: required", "age: must be >= 0"]
    - wrap_chain     → 500 WRAPPED            cause_chain 四层，最外层 → 根因
    - panic          → 500 INTERNAL           未捕获异常被兜底，recovered=true，进程必须存活
    - async_detached → 202 ACCEPTED           错误发生在脱离请求上下文的 asyncio task 里
  GET /stats → handled / unhandled / panics_recovered / last_unhandled / last_trace_id
  请求头 X-Trace-Id 必须原样回显。

Python 的取舍：
  - 异常自带 traceback，`raise ... from err` 能把 `__cause__` 串起来 —— 但**漏掉 `from`
    就只剩 `__context__`**：`traceback` 打出来看着一样，程序化的 cause 链却是断开的。
    这条连很多老手都会踩。
  - 没有 checked exception，函数签名不声明能抛什么：调用方只能靠文档/约定，
    漏掉的异常一路穿到最外层才被发现。
  - ⭐ 深水区：`asyncio.create_task` 的错误**没有任何运行时钩子** —— 不 await、
    不加 `add_done_callback`，它只在 task 被 GC 时打一行 "Task exception was never retrieved"，
    既不进你的日志体系，也不进你的指标。
"""

import asyncio
from typing import List, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

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

app = FastAPI(title="error-handling (python)")

PORT = 8157

STATE = {
    "handled": 0,
    "unhandled": 0,
    "panics": 0,
    "last_unhandled": "",
    "last_trace_id": "",
    "seq": 0,
}


class AppError(Exception):
    """带 code / HTTP 状态 / 字段级 details 的应用错误。"""

    def __init__(self, code: str, message: str, http_status: int, details: Optional[List[str]] = None):
        super().__init__(message)
        self.code = code
        self.http_status = http_status
        self.details = details or []


def body(kind: str, code: str, message: str, trace_id: str, chain: List[str],
         details: List[str], stack: bool, recovered: bool) -> dict:
    return {
        "kind": kind,
        "code": code,
        "message": message,
        "trace_id": trace_id,
        "cause_chain": chain,
        "details": details,
        "stack_present": stack,
        "recovered": recovered,
    }


def chain_of(exc: BaseException) -> List[str]:
    """沿 __cause__ 收集消息：最外层 → 根因。

    只认 __cause__（来自 raise ... from err）。__context__（"处理另一个异常时又抛了"）
    不进链：它不是因果关系，混进来会让 cause_chain 变得不可预期。
    """
    out: List[str] = []
    cur: Optional[BaseException] = exc
    while cur is not None and len(out) < 32:
        out.append(str(cur))
        cur = cur.__cause__
    return out


def trace_of(request: Request) -> str:
    tid = request.headers.get("x-trace-id")
    if tid:
        return tid
    STATE["seq"] += 1
    return "tid-%d" % STATE["seq"]


def make_wrapped() -> AppError:
    """构造四层链，并把最内层的 cause 挂到最外层的 AppError 上。"""
    try:
        try:
            try:
                raise RuntimeError("db: row 42 not found")
            except RuntimeError as err:
                raise RuntimeError("repository: load user") from err
        except RuntimeError as err:
            raise RuntimeError("service: get profile") from err
    except RuntimeError as err:
        top = AppError("WRAPPED", "handler: GET /errors/wrap_chain", 500)
        top.__cause__ = err
        return top


def on_detached_done(task: "asyncio.Task") -> None:
    """⭐ 深水区：这是唯一能观测到 detached task 错误的钩子。

    没有这一行，异常只在 task 被 GC 时打一行日志，既不进指标也不进告警。
    """
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        STATE["unhandled"] += 1
        STATE["last_unhandled"] = str(exc)


async def detached_work() -> None:
    await asyncio.sleep(0.12)
    raise RuntimeError("async-boom-17")


@app.middleware("http")
async def catch_unhandled(request: Request, call_next):
    """⭐ 深水区：Starlette 默认的 ServerErrorMiddleware 会在发完响应后把异常继续抛给
    uvicorn（日志里是完整 traceback，但响应体我们控制不了）。要给出结构化错误体，
    必须自己在最外层接住。
    """
    try:
        return await call_next(request)
    except AppError as exc:
        STATE["handled"] += 1
        chain = chain_of(exc)
        return JSONResponse(
            status_code=exc.http_status,
            content=body(request.url.path.rsplit("/", 1)[-1], exc.code, str(exc),
                         STATE["last_trace_id"], chain, exc.details, False, False),
        )
    except Exception as exc:
        STATE["handled"] += 1
        STATE["panics"] += 1
        chain = chain_of(exc)
        return JSONResponse(
            status_code=500,
            content=body("panic", "INTERNAL", str(exc), STATE["last_trace_id"],
                         chain, [], True, True),
        )


@app.get("/errors/{kind}")
async def errors(kind: str, request: Request) -> Response:
    tid = trace_of(request)
    STATE["last_trace_id"] = tid

    if kind == "not_found":
        raise AppError("NOT_FOUND", "user 42 not found", 404)

    if kind == "validation":
        raise AppError("VALIDATION_FAILED", "invalid request", 400,
                       ["email: required", "age: must be >= 0"])

    if kind == "wrap_chain":
        raise make_wrapped()

    if kind == "panic":
        # 未捕获异常：交给 catch_unhandled 兜底
        raise RuntimeError("boom-17")

    if kind == "async_detached":
        task = asyncio.create_task(detached_work())
        task.add_done_callback(on_detached_done)
        return JSONResponse(
            status_code=202,
            content=body("async_detached", "ACCEPTED", "async work spawned", tid, [], [], False, False),
        )

    msg = "unknown kind: " + kind
    return JSONResponse(status_code=404,
                        content=body(kind, "UNKNOWN_KIND", msg, tid, [msg], [], False, False))


@app.get("/stats")
async def stats() -> dict:
    return {
        "handled": STATE["handled"],
        "unhandled": STATE["unhandled"],
        "panics_recovered": STATE["panics"],
        "last_unhandled": STATE["last_unhandled"],
        "last_trace_id": STATE["last_trace_id"],
    }


if __name__ == "__main__":
    import uvicorn

    logger.info("service starting", port=PORT, title="error-handling")
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="debug")
