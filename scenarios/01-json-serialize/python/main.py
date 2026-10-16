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
    """POST /serialize — 对象 → JSON 字符串"""
    start = time.perf_counter()
    json_str = json.dumps(body)
    elapsed_us = int((time.perf_counter() - start) * 1_000_000)

    return {
        "json": json_str,
        "bytes": len(json_str.encode()),
        "time_us": elapsed_us,
        "pretty": json.dumps(body, indent=2),
    }


@app.post("/deserialize")
def deserialize(body: dict) -> dict:
    """POST /deserialize — JSON 字符串 → 对象"""
    json_string = body.get("json_string", "")
    start = time.perf_counter()
    parsed = json.loads(json_string)
    elapsed_us = int((time.perf_counter() - start) * 1_000_000)

    return {
        "parsed": parsed,
        "time_us": elapsed_us,
        "size": len(json_string),
    }


@app.post("/roundtrip")
def roundtrip(body: dict) -> dict:
    """POST /roundtrip — 往返保真测试"""
    json1 = json.dumps(body)
    parsed = json.loads(json1)
    json2 = json.dumps(parsed)

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
        last_json = json.dumps(user_dict)
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
    uvicorn.run(app, host="0.0.0.0", port=8092)
