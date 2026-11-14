"""
场景 06：轻量 RAG Demo — Python 实现 (FastAPI)

Python 版本特点：
1. 全部标准库 + FastAPI，无重型向量依赖
2. 词频向量 + cosine similarity（纯 Python 实现，numpy 可选）
3. Python 的字符串处理和正则比其他语言更方便
4. 和 Java/Go 完全相同的 pipeline
"""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import List, Dict, Optional
from collections import defaultdict

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
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

app = FastAPI(title="simple-rag-python", version="1.0.0")


# ==================== 向量存储 ====================

class Chunk:
    __slots__ = ("id", "text", "source", "vector")

    def __init__(self, id_: str, text: str, source: str):
        self.id = id_
        self.text = text
        self.source = source
        self.vector: List[float] = []


class RagStore:
    def __init__(self):
        self.chunks: Dict[str, Chunk] = {}
        self.vocab: List[str] = []  # 固定顺序词表

    # ---- 摄入 ----

    def ingest_file(self, file_path: str) -> int:
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        content = p.read_text(encoding="utf-8")
        file_name = p.name

        # 每次摄入重建 store（与 Go/Java/Rust/TS 一致：最后一次摄入的文档生效）
        self.chunks.clear()

        # 按空行切段落
        paragraphs = re.split(r"\n\s*\n", content)
        count = 0
        for i, para in enumerate(paragraphs):
            trimmed = para.strip()
            if len(trimmed) < 10:
                continue
            chunk_id = f"{file_name}#{i}"
            self.chunks[chunk_id] = Chunk(chunk_id, trimmed, file_name)
            count += 1

        self._rebuild_vectors()
        return count

    def _rebuild_vectors(self):
        # 收集所有词
        vocab_set: set[str] = set()
        for c in self.chunks.values():
            vocab_set.update(self._tokenize(c.text))

        # 按字母排序保证可预测
        self.vocab = sorted(vocab_set)

        # 给每个 chunk 生成向量
        for c in self.chunks.values():
            c.vector = self._build_vector(c.text)

    # ---- 检索 ----

    def search(self, question: str, top_k: int) -> List[Dict]:
        if not self.vocab:
            return []

        q_vec = self._build_vector(question)

        results: List[Dict] = []
        for c in self.chunks.values():
            score = self._cosine(q_vec, c.vector)
            if score > 0:
                results.append({
                    "text": c.text,
                    "source": c.source,
                    "score": round(score, 4),
                })

        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:top_k]

    # ---- 辅助 ----

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """分词：小写化 + 按非字母数字分割 + 过滤短词"""
        text = text.lower()
        tokens = re.split(r"[^a-z0-9\u4e00-\u9fff]+", text)
        return [t for t in tokens if len(t) >= 2]

    def _build_vector(self, text: str) -> List[float]:
        tokens = self._tokenize(text)
        freq: Dict[str, int] = defaultdict(int)
        for t in tokens:
            freq[t] += 1
        return [float(freq.get(w, 0)) for w in self.vocab]

    @staticmethod
    def _cosine(a: List[float], b: List[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    # ---- 状态 ----

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)

    @property
    def vocab_size(self) -> int:
        return len(self.vocab)


store = RagStore()


# ==================== Mock 生成答案 ====================

def mock_answer(question: str, sources: List[Dict]) -> str:
    if not sources:
        return "我没有找到相关信息，请先 POST /ingest 摄入文档。"
    # 答案格式与其余四门逐字节一致：头部 + 每行一条来源（行尾带换行、相关度固定 4 位小数）
    out = f"根据摄入的文档，关于「{question}」的相关内容：\n\n"
    for i, s in enumerate(sources):
        out += f"{i + 1}. (来自 {s['source']}, 相关度 {s['score']:.4f}) {s['text']}\n"
    return out


# ==================== API 模型 ====================

class IngestReq(BaseModel):
    file_path: str


class AskReq(BaseModel):
    question: str
    top_k: int = 3


# ==================== 端点 ====================

@app.exception_handler(RequestValidationError)
async def validation_error_handler(request, exc: RequestValidationError):
    """把 pydantic 的 422 统一改写为 400（与其余四门一致：请求体缺字段/类型错都算客户端错误）"""
    return JSONResponse(status_code=400, content={"success": False, "error": "参数校验失败"})


@app.post("/ingest")
def ingest(req: IngestReq):
    try:
        chunks = store.ingest_file(req.file_path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except OSError as e:
        # 目录/权限等读失败同样是客户端给的 path 不对 → 400（与 Java/Rust/TS 一致）
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "success": True,
        "file": req.file_path,
        "chunks": chunks,
        "embeddings_generated": chunks,
        "vocab_size": store.vocab_size,
    }


@app.post("/ask")
def ask(req: AskReq):
    # top_k 必须 >= 1（0/负数对其他语言分别是 panic / 截断异常，统一按 400 拒绝）
    if req.top_k < 1:
        raise HTTPException(status_code=400, detail="top_k 必须 >= 1")
    sources = store.search(req.question, req.top_k)
    answer = mock_answer(req.question, sources)

    return {
        "success": True,
        "question": req.question,
        "answer": answer,
        "sources": sources,
        "mode": "local-mock",
    }


@app.get("/health")
def health():
    return {
        "service": "simple-rag-python",
        "chunks_loaded": store.chunk_count,
        "vocab_size": store.vocab_size,
    }


if __name__ == "__main__":
    import uvicorn

    logger.info("service starting", port=8102, title="simple-rag-python")
    uvicorn.run(app, host="0.0.0.0", port=8102, log_level="debug")
