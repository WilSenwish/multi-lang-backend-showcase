# 场景 06：轻量 RAG Demo（Agent 亮点）

## 业务描述

统一实现一个极简的 **Retrieval Augmented Generation (RAG)** Demo：

1. **摄入文档**：将本地 Markdown 文件转为向量嵌入存入向量存储
2. **查询问答**：用户提问 → 检索相关文档片段 → 调用 LLM 生成答案

### 统一接口

```bash
# 1. 摄入文档
POST /ingest
{
  "file_path": "./docs/philosophy.md"
}
→ {"chunks": 24, "embeddings_generated": 24}

# 2. 问答
POST /ask
{
  "question": "Rust 的所有权是什么？"
}
→ {
    "answer": "所有权系统是 Rust 的核心特性...",
    "sources": [
      {"text": "...", "score": 0.92, "file": "philosophy.md"}
    ]
  }
```

### 技术依赖
- **LLM API**：OpenAI 兼容接口（支持 Ollama 本地模型）
- **向量嵌入**：优先用 LLM API 的 embedding 能力
- **向量存储**：简化实现，用内存 + cosine similarity（不引入外部向量数据库）

所有语言实现**业务逻辑完全一致**。

---

## 实现清单

| 语言 | HTTP 服务 | LLM 客户端 | 向量计算 |
|------|----------|-----------|---------|
| Java | Spring Boot Web | Spring AI | 手写 cosine similarity |
| Go | `net/http` | `net/http` + OpenAI API | 手写 |
| Python | FastAPI | `httpx` + OpenAI API | numpy |
| Rust | axum | `reqwest` + `serde_json` | 手写（ndarray 可选） |
| TS(Node) | fastify | OpenAI SDK | 手写 |

### 特别关注
- 这是仓库**亮点场景**，贴合 Agent / AI 开发方向
- 各语言调用 LLM API 的方式、错误处理、流式输出（可选）
- 向量计算性能差异

---

## 关键对比

| 维度 | Java | Go | Python | Rust | TS(Node) |
|------|------|----|--------|------|----------|
| **HTTP 服务** | | | | | |
| **LLM 客户端** | | | | | |
| **异步调用** | | | | | |
| **向量计算** | | | | | |
| **性能** | | | | | |
| **优势** | | | | | |
| **痛点 & 坑** | | | | | |

---

## 运行方式

<!-- TODO: 实现后补充启动/运行命令 -->

### Java
```bash
# TODO
```

### Go
```bash
# TODO
```

### Python
```bash
# TODO
```

### Rust
```bash
# TODO
```

### TS(Node)
```bash
# TODO
```

---

## 选型思考

<!-- TODO: 实现后补充选型建议 -->

