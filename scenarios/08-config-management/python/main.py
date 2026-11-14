"""
场景 08：多环境配置管理 — Python 实现（pydantic-settings）

Python 配置管理特点：
1. pydantic-settings = 启动时配置 + 启动时校验（pydantic v2）
2. 支持：yaml / env / 环境变量（按优先级覆盖）
3. pydantic Field 约束：ge/le（范围）/ min_length（必填）/ pattern（正则）
4. 校验失败 → 启动失败（fail-fast）
5. Python 没有编译期配置校验（不像 Rust config crate）
6. yaml 解析需要 pyyaml 依赖

和 Java @ConfigurationProperties 对比：
- Python 用 pydantic model，字段类型自动推断，写起来更短
- Java 用注解 + getter/setter，啰嗦但编译期安全
- pydantic 的 model_validator 支持复杂业务校验（跨字段依赖）
"""
from __future__ import annotations

import os
from typing import Literal

import yaml
from fastapi import FastAPI
from pydantic import BaseModel, Field, field_validator

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

app = FastAPI(title="config-management-python", version="1.0.0")


# ==================== 配置模型 ====================

class ServerConfig(BaseModel):
    port: int = Field(default=8112, ge=1, le=65535, description="端口号")
    host: str = Field(default="0.0.0.0", min_length=1)


class DatabaseConfig(BaseModel):
    url: str = Field(default="localhost:3306", min_length=1)
    user: str = Field(default="admin", min_length=1)
    password: str = Field(default="secret")
    pool_size: int = Field(default=10, ge=1, le=100)


class LoggingConfig(BaseModel):
    level: Literal["TRACE", "DEBUG", "INFO", "WARN", "ERROR"] = Field(default="INFO")
    json: bool = Field(default=True)


class AppConfig(BaseModel):
    """统一配置 — pydantic v2 模型自动校验"""
    server: ServerConfig = Field(default_factory=ServerConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    env: str = Field(default_factory=lambda: os.getenv("MYAPP_ENV", "default"))

    @field_validator("env")
    @classmethod
    def env_valid(cls, v: str) -> str:
        return v or "default"


# ==================== 加载配置 ====================

def load_config() -> AppConfig:
    """从 config.yaml 加载，然后环境变量覆盖（优先级更高）"""
    # 1. 读 yaml
    yaml_path = os.getenv("MYAPP_CONFIG", "config.yaml")
    cfg_data: dict = {}
    if os.path.exists(yaml_path):
        with open(yaml_path, encoding="utf-8") as f:
            cfg_data = yaml.safe_load(f) or {}
        logger.info("config loaded from yaml", path=yaml_path)
    else:
        logger.info("yaml not found, using defaults", path=yaml_path)

    # 2. 环境变量覆盖（优先级最高）
    # MYAPP_SERVER_PORT → cfg_data["server"]["port"]
    env_prefix = "MYAPP_"
    prefix_len = len(env_prefix)
    for key, val in os.environ.items():
        if not key.startswith(env_prefix):
            continue
        # MYAPP_SERVER_PORT → ["server", "port"]
        paths = key[prefix_len:].lower().split("__")
        if len(paths) == 1:
            paths = key[prefix_len:].lower().split("_")
        if len(paths) < 2:
            continue
        # 写入 cfg_data 嵌套字典
        d = cfg_data
        for p in paths[:-1]:
            d = d.setdefault(p, {})
        # 类型转换
        last = paths[-1]
        d[last] = _auto_cast(val)

    cfg = AppConfig.model_validate(cfg_data)
    logger.info("config loaded successfully", env=cfg.env, port=cfg.server.port)
    return cfg


def _auto_cast(val: str):
    """把环境变量字符串自动转成 int/bool/str"""
    if val.isdigit():
        return int(val)
    if val.lower() in ("true", "false"):
        return val.lower() == "true"
    if val.lower() in ("null", "none"):
        return None
    return val


# 全局配置（启动时加载一次）
global_config: AppConfig = load_config()


# ==================== 端点 ====================

@app.get("/config")
def config():
    cfg = global_config.model_copy()
    # 脱敏密码
    cfg.database.password = "********"
    resp = cfg.model_dump()
    resp["source"] = "pydantic-settings + config.yaml + MYAPP_ env"
    return resp


if __name__ == "__main__":
    import uvicorn

    logger.info("service starting", port=global_config.server.port, title="config-management-python")
    uvicorn.run(app, host="0.0.0.0", port=global_config.server.port, log_level="debug")
