"""
scenarios/00-hello-http Python 实现 (FastAPI + Pydantic)

统一 API 契约:
    GET /hello?name={xxx}
    → {"msg": "hello {xxx}"}
    → {"msg": "hello world"}  # name 缺省
"""
from fastapi import FastAPI
from pydantic import BaseModel

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

app = FastAPI(title="hello-http-python", version="1.0.0")

DEFAULT_NAME = "world"


class HelloResponse(BaseModel):
    """统一响应 DTO"""
    msg: str


@app.get("/hello", response_model=HelloResponse)
async def hello(name: str | None = None) -> HelloResponse:
    """
    Hello 接口
    :param name: 可选参数，缺省返回 hello world
    """
    target = name if name else DEFAULT_NAME
    return HelloResponse(msg=f"hello {target}")


if __name__ == "__main__":
    import uvicorn

    logger.info("service starting", port=8082, title="hello-http-python")
    uvicorn.run(app, host="0.0.0.0", port=8082, log_level="debug")
