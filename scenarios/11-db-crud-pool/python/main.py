"""
场景 11：数据库 CRUD + 连接池 — Python 实现（SQLAlchemy 2.0 + FastAPI）

Python DB 特点：
1. SQLAlchemy 2.0：声明式 ORM + 核心表达式（最流行的 Python DB 库）
2. SQLAlchemy 内置连接池（QueuePool）：pool_size / max_overflow / pool_recycle
3. SQLite 零依赖本地运行
4. FastAPI + Pydantic model 自动校验

和 Java/GORM 对比：
- SQLAlchemy 2.0 支持 sync 和 async
- Pydantic model 既是 API 输入输出又是类型校验
- Python 动态类型在 ORM 里灵活但不编译期检查
"""
from __future__ import annotations

import time
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, DateTime, func
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

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

# ==================== DB 配置 ====================

DATABASE_URL = "sqlite:///./demo_py.db"

# SQLAlchemy 连接池配置
# SQLite 用 NullPool（不需要真正的连接池，单文件数据库）
# 但为了统一对比，还是配置 QueuePool
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # SQLite 多线程支持
    pool_pre_ping=True,
    pool_recycle=1800,  # 连接生命周期 30min
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


# ==================== ORM 模型 ====================

class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False)
    email = Column(String(128), nullable=True)
    age = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


# 自动建表
Base.metadata.create_all(bind=engine)

app = FastAPI(title="db-crud-pool-python", version="1.0.0")


# ==================== Pydantic Schema ====================

class UserCreate(BaseModel):
    name: str
    email: Optional[str] = None
    age: Optional[int] = None


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    age: Optional[int] = None


class UserResponse(BaseModel):
    id: int
    name: str
    email: Optional[str]
    age: Optional[int]
    created_at: Optional[str] = None


class UserList(BaseModel):
    items: list[UserResponse]
    total: int
    page: int
    size: int


# ==================== CRUD ====================

@app.post("/users", response_model=UserResponse, status_code=201)
def create_user(data: UserCreate):
    with SessionLocal() as session:
        user = User(name=data.name, email=data.email, age=data.age)
        session.add(user)
        session.commit()
        session.refresh(user)
        return _to_response(user)


@app.get("/users/{user_id}", response_model=UserResponse)
def get_user(user_id: int):
    with SessionLocal() as session:
        user = session.get(User, user_id)
        if not user:
            raise HTTPException(404, "not found")
        return _to_response(user)


@app.get("/users", response_model=UserList)
def list_users(page: int = 0, size: int = 10):
    with SessionLocal() as session:
        total = session.query(User).count()
        items = session.query(User).order_by(User.id.asc()).offset(page * size).limit(size).all()
        return UserList(
            items=[_to_response(u) for u in items],
            total=total,
            page=page,
            size=size,
        )


@app.put("/users/{user_id}", response_model=UserResponse)
def update_user(user_id: int, data: UserUpdate):
    with SessionLocal() as session:
        user = session.get(User, user_id)
        if not user:
            raise HTTPException(404, "not found")
        if data.name is not None:
            user.name = data.name
        if data.email is not None:
            user.email = data.email
        if data.age is not None:
            user.age = data.age
        session.commit()
        session.refresh(user)
        return _to_response(user)


@app.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: int):
    with SessionLocal() as session:
        user = session.get(User, user_id)
        if not user:
            raise HTTPException(404, "not found")
        session.delete(user)
        session.commit()


@app.get("/health")
def health():
    return {"service": "db-crud-pool-python", "db": "sqlite"}


def _to_response(u: User) -> UserResponse:
    return UserResponse(
        id=u.id,
        name=u.name,
        email=u.email,
        age=u.age,
        created_at=u.created_at.isoformat() if u.created_at else None,
    )


if __name__ == "__main__":
    import uvicorn

    logger.info("service starting", port=8127, title="db-crud-pool-python")
    uvicorn.run(app, host="0.0.0.0", port=8127, log_level="debug")
