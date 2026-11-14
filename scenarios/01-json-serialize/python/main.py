"""
场景 01：JSON 序列化/反序列化 — Python 实现 (FastAPI + Pydantic v2)

Pydantic v2 特点（和 Java Jackson / Rust serde 对比）：
1. 运行时类型校验（Java/Rust 编译期，Python 动态类型所以只能运行时）
2. model_dump() 序列化，model_validate() 反序列化
3. 默认 null 处理：Optional[str] = None → JSON null
4. 默认值：List[str] = [] → JSON []
5. 类型校验会自动转换（输入 int 但字段 str → 报错或自动转）
6. v2 用 Rust 核心，性能比 v1 快 5-10x

和 Java Jackson 的关键差异：
- Java Jackson null 字段默认输出，Pydantic 默认也输出（除非 exclude_none=True）
- Java 空集合 → [], Pydantic 空 list → [] 一样
- 字段名映射：Java @JsonProperty，Pydantic Field(alias=...) 或 model_config
"""
from __future__ import annotations

import json
import time
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from pydantic.alias_generators import to_camel

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

app = FastAPI(title="json-serialize-python", version="1.0.0")


class Address(BaseModel):
    """嵌套地址结构"""
    model_config = ConfigDict(populate_by_name=True)
    city: str
    zip: str


class User(BaseModel):
    """测试用 User 结构

    Pydantic 类型声明：
    - Optional[str] = None → JSON 输出 null（如果有值就输出值）
    - List[str] = [] → JSON 输出 []
    """
    model_config = ConfigDict(populate_by_name=True)

    id: int
    name: str
    email: Optional[str] = None    # 默认 None → JSON null
    age: int
    tags: list[str]
    address: Address
    scores: list[int] = []          # 默认空列表 → JSON []


def demo_user() -> User:
    """构造标准测试对象"""
    return User(
        id=1,
        name="Alice",
        email=None,                  # → JSON null
        age=28,
        tags=["engineer", "java"],
        address=Address(city="Beijing", zip="100000"),
        scores=[],                   # → JSON []
    )


# ==================== 5 个端点 ====================

@app.get("/demo")
def demo() -> User:
    """GET /demo — 返回标准测试 JSON"""
    return demo_user()


@app.post("/serialize")
def serialize(body: dict) -> dict:
    """POST /serialize — 对象 → JSON 字符串

    契约规定的规范形式：紧凑分隔符 + 非 ASCII 不转义（ensure_ascii=False）。
    Python 的 json.dumps 默认会把非 ASCII 转义成 \\uXXXX，与另外四门语言不一致。
    """
    start = time.perf_counter()
    json_str = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    elapsed_us = int((time.perf_counter() - start) * 1_000_000)

    return {
        "json": json_str,
        "bytes": len(json_str.encode()),
        "time_us": elapsed_us,
        "pretty": json.dumps(body, ensure_ascii=False, indent=2),
    }


@app.post("/deserialize")
def deserialize(body: dict) -> dict:
    """POST /deserialize — JSON 字符串 → 对象

    size 的契约口径是 **UTF-8 字节数**（与 Go len() / Java getBytes().length() /
    Rust String::len() / TS Buffer.byteLength() 一致）；Python 的 len(str) 是字符数，
    含非 ASCII 时会偏小，必须 encode 后取长度。
    """
    json_string = body.get("json_string", "")
    start = time.perf_counter()
    parsed = json.loads(json_string)
    elapsed_us = int((time.perf_counter() - start) * 1_000_000)

    return {
        "parsed": parsed,
        "time_us": elapsed_us,
        "size": len(json_string.encode("utf-8")),
    }


@app.post("/roundtrip")
def roundtrip(body: dict) -> dict:
    """POST /roundtrip — 往返保真测试

    与 /serialize 同一套规范形式：紧凑分隔符 + ensure_ascii=False，
    否则 original_json 会带上空格与 \\uXXXX 转义，和另外四门语言逐字节比对不上。
    """
    json1 = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    parsed = json.loads(json1)
    json2 = json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))

    return {
        "original_json": json1,
        "roundtrip_json": json2,
        "equal": json1 == json2,
        "original_bytes": len(json1.encode()),
        "roundtrip_bytes": len(json2.encode()),
    }


@app.get("/bench")
def bench() -> dict:
    """GET /bench — 10000 次 serialize + deserialize 性能基准"""
    user = demo_user()
    iterations = 10000

    # Pydantic model_dump / model_validate 方式的基准
    user_dict = user.model_dump()

    # 预热
    for _ in range(100):
        s = json.dumps(user_dict)
        json.loads(s)

    start = time.perf_counter()
    last_json = ""
    for _ in range(iterations):
        # 与 /serialize 同一套规范形式：紧凑 + 不转义非 ASCII。
        # json_size_bytes 的契约是"规范序列化后的字节数"，用默认分隔符会偏大。
        last_json = json.dumps(user_dict, ensure_ascii=False, separators=(",", ":"))
        json.loads(last_json)
    total_ms = int((time.perf_counter() - start) * 1000)

    return {
        "language": "python-pydantic",
        "iterations": iterations,
        "total_time_ms": total_ms,
        "avg_time_us": round(total_ms * 1000 / iterations, 2),
        "json_size_bytes": len(last_json.encode()),
    }


if __name__ == "__main__":
    import uvicorn

    logger.info("service starting", port=8092, title="json-serialize-python")
    uvicorn.run(app, host="0.0.0.0", port=8092, log_level="debug")
