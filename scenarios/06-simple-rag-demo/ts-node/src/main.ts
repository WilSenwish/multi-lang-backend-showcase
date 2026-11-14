/**
 * 场景 06：轻量 RAG Demo — TS(Node) 实现 (fastify)
 *
 * TS Node 版本特点：
 * 1. 全部 Node 原生 API + fastify，零重型依赖
 * 2. 和其他语言完全相同的 pipeline
 * 3. TS 类型安全让向量存储操作更安全
 * 4. Node 的单线程模型 + libuv 异步，IO 密集（文件摄入）效率高
 */
import Fastify from 'fastify';
import pino from 'pino';
import * as fs from 'fs';
import * as path from 'path';

const PORT = 8104;

// pino 初始化：JSON 格式 + stdout + 最低 DEBUG 级别
const logger = pino({
  level: process.env.LOG_LEVEL || 'debug',
  timestamp: pino.stdTimeFunctions.isoTime,
  transport: { target: 'pino/file', options: { destination: 1 } }
});

// ==================== 数据结构 ====================

interface Chunk {
  id: string;
  text: string;
  source: string;
  vector: number[];
}

interface SourceResult {
  text: string;
  source: string;
  score: number;
}

class RagStore {
  private chunks: Map<string, Chunk> = new Map();
  private vocab: string[] = [];

  // ---- 摄入 ----

  ingestFile(filePath: string): number {
    if (!fs.existsSync(filePath)) {
      throw new Error(`文件不存在: ${filePath}`);
    }

    const content = fs.readFileSync(filePath, 'utf-8');
    const fileName = path.basename(filePath);

    this.chunks.clear();

    // 按空行切段落
    const paragraphs = content.split(/\n\s*\n/);
    let count = 0;
    paragraphs.forEach((para, i) => {
      const trimmed = para.trim();
      if (trimmed.length < 10) return;
      const id = `${fileName}#${i}`;
      this.chunks.set(id, { id, text: trimmed, source: fileName, vector: [] });
      count++;
    });

    this.rebuildVectors();
    return count;
  }

  private rebuildVectors(): void {
    // 收集所有词
    const vocabSet = new Set<string>();
    for (const c of this.chunks.values()) {
      for (const w of tokenize(c.text)) {
        vocabSet.add(w);
      }
    }
    this.vocab = Array.from(vocabSet).sort();

    // 给每个 chunk 生成向量
    for (const c of this.chunks.values()) {
      c.vector = buildVector(c.text, this.vocab);
    }
  }

  // ---- 检索 ----

  search(question: string, topK: number): SourceResult[] {
    if (this.vocab.length === 0) return [];

    const qVec = buildVector(question, this.vocab);
    const results: SourceResult[] = [];

    for (const c of this.chunks.values()) {
      const score = cosineSimilarity(qVec, c.vector);
      if (score > 0) {
        results.push({
          text: c.text,
          source: c.source,
          score: Math.round(score * 10000) / 10000,
        });
      }
    }

    results.sort((a, b) => b.score - a.score);
    return results.slice(0, topK);
  }

  // ---- 状态 ----

  get chunkCount(): number { return this.chunks.size; }
  get vocabSize(): number { return this.vocab.length; }
}

// ==================== 辅助函数 ====================

function tokenize(text: string): string[] {
  const lower = text.toLowerCase();
  const tokens = lower
    .split(/[^a-z0-9\u4e00-\u9fff]+/)
    .filter(t => [...t].length >= 2); // 按 Unicode 字符长度过滤
  return tokens;
}

function buildVector(text: string, vocab: string[]): number[] {
  const tokens = tokenize(text);
  const freq = new Map<string, number>();
  for (const t of tokens) {
    freq.set(t, (freq.get(t) || 0) + 1);
  }
  return vocab.map(w => freq.get(w) || 0);
}

function cosineSimilarity(a: number[], b: number[]): number {
  let dot = 0, normA = 0, normB = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i];
    normA += a[i] * a[i];
    normB += b[i] * b[i];
  }
  if (normA === 0 || normB === 0) return 0;
  return dot / (Math.sqrt(normA) * Math.sqrt(normB));
}

function mockAnswer(question: string, sources: SourceResult[]): string {
  if (sources.length === 0) {
    return '我没有找到相关信息，请先 POST /ingest 摄入文档。';
  }
  // 格式与其余四门逐字节一致：头部 + 每行一条来源（行尾带换行、相关度固定 4 位小数）
  let out = `根据摄入的文档，关于「${question}」的相关内容：\n\n`;
  sources.forEach((s, i) => {
    out += `${i + 1}. (来自 ${s.source}, 相关度 ${s.score.toFixed(4)}) ${s.text}\n`;
  });
  return out;
}

// ==================== Fastify 服务 ====================

const store = new RagStore();
const fastify = Fastify({ logger });

interface IngestBody { file_path: string; }
interface AskBody { question: string; top_k?: number; }

/** 方法不匹配时返回 405（fastify 的 .post/.get 默认给 404，与其余四门不一致） */
function methodGuard(request: any, reply: any, allow: string): boolean {
  if (request.method !== allow) {
    reply.code(405);
    return false;
  }
  return true;
}

// POST /ingest
fastify.all('/ingest', async (request, reply) => {
  if (!methodGuard(request, reply, 'POST')) return { error: 'method not allowed' };
  const { file_path } = request.body as IngestBody;
  if (typeof file_path !== 'string' || file_path.length === 0) {
    reply.code(400);
    return { success: false, error: '缺少 file_path' };
  }
  try {
    const chunks = store.ingestFile(file_path);
    return {
      success: true,
      file: file_path,
      chunks,
      embeddings_generated: chunks,
      vocab_size: store.vocabSize,
    };
  } catch (err: any) {
    // 文件不存在/是目录/权限问题都是客户端给的 path 不对 → 400（与其余四门一致）
    reply.code(400);
    return { success: false, error: err.message };
  }
});

// POST /ask
fastify.all('/ask', async (request, reply) => {
  if (!methodGuard(request, reply, 'POST')) return { error: 'method not allowed' };
  const { question, top_k = 3 } = request.body as AskBody;
  // question 缺失/类型错 → 400；空串是合法输入（检索不到内容，返回兜底答案）
  if (typeof question !== 'string') {
    reply.code(400);
    return { success: false, error: '缺少 question' };
  }
  // top_k 必须是 >= 1 的整数（0/负数与其余四门一起按 400 拒绝）
  if (!Number.isInteger(top_k) || top_k < 1) {
    reply.code(400);
    return { success: false, error: 'top_k 必须 >= 1' };
  }
  const sources = store.search(question, top_k);
  const answer = mockAnswer(question, sources);
  return {
    success: true,
    question,
    answer,
    sources,
    mode: 'local-mock',
  };
});

// GET /health
fastify.all('/health', async (request, reply) => {
  if (!methodGuard(request, reply, 'GET')) return { error: 'method not allowed' };
  return {
    service: 'simple-rag-ts-node',
    chunks_loaded: store.chunkCount,
    vocab_size: store.vocabSize,
  };
});

const startServer = async () => {
  try {
    await fastify.listen({ port: PORT, host: '0.0.0.0' });
    logger.info({ msg: 'server starting', addr: `0.0.0.0:${PORT}` });
  } catch (err) {
    logger.error({ err }, 'server failed to start');
    process.exit(1);
  }
};

startServer();
