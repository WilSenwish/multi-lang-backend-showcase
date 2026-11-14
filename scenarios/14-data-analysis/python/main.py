"""场景 14：数据分析处理（pandas 主场）。

数据集是"行号 i 的纯函数"（LCG 高 32 位 → amount，i % categories → category），
五种语言生成完全一致的数据，因此聚合结果可以做跨语言契约级比对。

分位数统一采用 nearest-rank 口径（排序后取 ceil(p*n/100)-1 下标），
原因：pandas quantile 默认 linear 插值、polars 默认 nearest、各库口径不一，
若放任各自的默认值，跨语言结果必然对不齐。
"""

import math
import time

import pandas as pd
from fastapi import FastAPI
from pydantic import BaseModel, Field

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

app = FastAPI(title="data-analysis")

MULT = 6364136223846793005
INC = 1442695040888963407
MASK = (1 << 64) - 1
AMOUNT_MOD = 100_000


def amount_of(i: int) -> int:
    h = ((i + 1) * MULT + INC) & MASK
    return (h >> 32) % AMOUNT_MOD


def nearest_rank(sorted_vals: list[int], p: int) -> int:
    """nearest-rank 分位数：排序后取下标 ceil(p*n/100)-1。"""
    n = len(sorted_vals)
    idx = math.ceil(p * n / 100) - 1
    idx = max(0, min(n - 1, idx))
    return sorted_vals[idx]


class AnalyzeRequest(BaseModel):
    rows: int = Field(default=200_000, ge=1_000, le=2_000_000)
    categories: int = Field(default=8, ge=1, le=64)


class GroupStat(BaseModel):
    category: str
    count: int
    sum: int
    avg: float
    p50: int
    p95: int


class TopRow(BaseModel):
    id: int
    category: str
    amount: int


class AnalyzeResponse(BaseModel):
    rows: int
    categories: int
    groups: list[GroupStat]
    top10: list[TopRow]
    gen_ms: int
    agg_ms: int
    elapsed_ms: int


@app.get("/health")
def health() -> dict:
    return {"service": "data-analysis", "lang": "python", "engine": "pandas"}


@app.post("/analyze")
def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    t0 = time.perf_counter()

    # ---- 数据生成（与其它语言逐位一致）----
    ids = list(range(req.rows))
    cats = [f"cat-{i % req.categories}" for i in ids]
    amounts = [amount_of(i) for i in ids]
    df = pd.DataFrame({"id": ids, "category": cats, "amount": amounts})

    t1 = time.perf_counter()

    # ---- 聚合：一行 groupby 的事（这是 pandas 的主场）----
    groups: list[GroupStat] = []
    for cat, sub in df.groupby("category", sort=True):
        n = len(sub)
        s = int(sub["amount"].sum())
        vals = sorted(sub["amount"].tolist())
        groups.append(
            GroupStat(
                category=str(cat),
                count=n,
                sum=s,
                avg=s / n,
                p50=nearest_rank(vals, 50),
                p95=nearest_rank(vals, 95),
            )
        )

    # ---- Top-10：amount 降序，id 升序 ----
    top_df = df.sort_values(["amount", "id"], ascending=[False, True]).head(10)
    top10 = [
        TopRow(id=int(r.id), category=str(r.category), amount=int(r.amount))
        for r in top_df.itertuples(index=False)
    ]

    t2 = time.perf_counter()
    return AnalyzeResponse(
        rows=req.rows,
        categories=req.categories,
        groups=groups,
        top10=top10,
        gen_ms=round((t1 - t0) * 1000),
        agg_ms=round((t2 - t1) * 1000),
        elapsed_ms=round((t2 - t0) * 1000),
    )


if __name__ == "__main__":
    import uvicorn

    PORT = 8142
    logger.info("service starting", port=PORT, title="data-analysis")
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="debug")
