"""
scenarios/00-hello-http Python 实现 (FastAPI + Pydantic)

统一 API 契约:
    GET /hello?name={xxx}
    → {"msg": "hello {xxx}"}
    → {"msg": "hello world"}  # name 缺省
"""
from fastapi import FastAPI
from pydantic import BaseModel

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
    uvicorn.run(app, host="0.0.0.0", port=8082)
