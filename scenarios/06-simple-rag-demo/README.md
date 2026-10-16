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

### 技术依赖（极简方案）

- **向量存储**：内存 Map，不引入外部数据库 ✅ 零依赖
- **向量检索**：手写 cosine similarity ✅ 零依赖
- **文档切分**：按段落切分（空行分割 Markdown） ✅ 零依赖
- **向量生成 + LLM 调用**：
  - **优先**：`LLM_API_URL` + `LLM_API_KEY` 环境变量（OpenAI 兼容接口）
  - **Fallback**：本地 mock — 关键词匹配检索片段 + 模板化回答（无需外部 API 也能跑）
- 所有依赖通过环境变量控制，不强制要求

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
| **端口** | 8100 | 8101 | 8102 | 8103 | 8104 |
| **HTTP 服务** | SpringBoot | net/http | FastAPI | axum | fastify |
| **向量存储** | `ConcurrentHashMap` | `map + sync.RWMutex` | 普通 dict | `Mutex<Vec<Chunk>>` | `Map<string, Chunk>` |
| **向量生成** | 词频 TF（纯手写） | 词频 TF（纯手写） | 词频 TF（纯手写） | 词频 TF（纯手写） | 词频 TF（纯手写） |
| **向量检索** | cosine similarity 手写 | cosine similarity 手写 | cosine similarity 手写 | cosine similarity 手写 | cosine similarity 手写 |
| **异步调用** | SpringBoot 同步线程池 | 同步 + goroutine | FastAPI 自动线程池 | tokio async（虽当前是同步向量计算） | Node 单线程异步 |
| **文件摄入** | `Files.readString` | `os.ReadFile` | `Path.read_text` | `fs::read_to_string` | `fs.readFileSync` |
| **中文分词** | `[\u4e00-\u9fff]+` regex | 同 Java | 同 Java | `is_alphanumeric` + Unicode range | 同 Java |
| **向量计算性能** | JIT 编译快，GC 有小开销 | **极快**（原生） | 慢（Python 循环慢，numpy 可加速） | **最快**（零 GC） | JIT 快，但单线程 |
| **零外部依赖** | ⚠️ SpringBoot 重 | ✅ 纯标准库 | ⚠️ FastAPI 依赖 | ✅ axum + serde 必要 | ⚠️ fastify 依赖 |
| **Lint 安全** | SpringBoot 自动注入 | Mutex 保护 | GIL 天然线程安全 | Mutex 保护（编译期安全） | 单线程无竞争 |
| **优势** | 和 Spring 生态无缝 | 极简、零依赖、并发安全 | 字符串处理 + 正则最方便 | 性能极致 + 编译期安全 | TS 类型安全 + Node 生态 |
| **痛点 & 坑** | SpringBoot 启动慢 | 向量计算锁粒度大（全 store 锁） | 纯 Python 向量计算慢（上 numpy） | Rust 写正则比其他语言啰嗦 | Node 单线程，大向量阻塞事件循环 |

---

## 统一 API（3 个端点）

### `POST /ingest` — 摄入文档
```bash
curl -s -X POST http://localhost:8100/ingest \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"../docs/philosophy.md"}'
→ {"success":true,"file":"...","chunks":24,"embeddings_generated":24,"vocab_size":320}
```

### `POST /ask` — 问答
```bash
curl -s -X POST http://localhost:8100/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"Rust 的所有权是什么？","top_k":3}'
→ {"answer":"根据摄入的文档...","sources":[...]}
```

### `GET /health` — 状态
```bash
curl -s http://localhost:8100/health
→ {"service":"simple-rag-java","chunks_loaded":24,"vocab_size":320}
```

---

## 运行方式

### Java (端口 8100)
```bash
cd scenarios/06-simple-rag-demo/java
mise exec -- mvn spring-boot:run
```

### Go (端口 8101)
```bash
cd scenarios/06-simple-rag-demo/go
go run main.go
```

### Python (端口 8102)
```bash
cd scenarios/06-simple-rag-demo/python
pip install -r requirements.txt
uvicorn main:app --port 8102
```

### Rust (端口 8103)
```bash
cd scenarios/06-simple-rag-demo/rust
cargo run
```

### TS(Node) (端口 8104)
```bash
cd scenarios/06-simple-rag-demo/ts-node
npm install && npm run dev
```

### 批量测试
```bash
# 1. 摄入一份 Markdown（比如仓库自己的 docs/philosophy.md）
for port in 8100 8101 8102 8103 8104; do
  echo "=== Port $port ==="
  curl -s -X POST http://localhost:$port/ingest \
    -H 'Content-Type: application/json' \
    -d '{"file_path":"docs/philosophy.md"}' | jq -c .
done

# 2. 统一问答
echo "=== 统一问答测试 ==="
for port in 8100 8101 8102 8103 8104; do
  echo "--- Port $port ---"
  curl -s -X POST http://localhost:$port/ask \
    -H 'Content-Type: application/json' \
    -d '{"question":"Go 的 goroutine 是什么？"}' | jq -r '.answer'
done
```

---

## 选型思考

### RAG 系统各语言定位

| 场景 | 推荐 | 原因 |
|------|------|------|
| **Java/Spring 项目内嵌 RAG** | ☕ Java | 和 Spring AI 无缝集成，已有项目复用 |
| **云原生 RAG 微服务** | 🐹 Go 或 🦀 Rust | 单文件二进制、无 GC、启动快 |
| **AI 数据处理 + RAG** | 🐍 Python | numpy/scipy 向量计算极快，生态最全 |
| **Agent / AI 工具链** | 🦀 Rust | 编译期安全、性能极致，Rust 在 AI infra 越来越火 |
| **全栈 TS RAG 服务** | 🟦 Node | BFF 层调用 LLM API，TS 类型安全 |

### 关键选型决策点

| 问题 | 答案 |
|------|------|
| **向量库选什么？** | 内存（demo）→ Chroma / Faiss（单机）→ Milvus / pgvector（生产） |
| **向量嵌入 API？** | OpenAI text-embedding-3-small / Ollama 本地 / BGE-M3（中文强） |
| **Python 向量计算慢怎么办？** | 用 numpy 或 faiss，纯 Python 循环慢 100x |
| **Rust 写 RAG 的优势？** | 向量计算 + 文档处理 + HTTP 服务全栈性能碾压，且无 GC |
| **这个 demo 的局限性？** | 词频向量只是 TF，真正 RAG 用 embedding（语义理解） |

