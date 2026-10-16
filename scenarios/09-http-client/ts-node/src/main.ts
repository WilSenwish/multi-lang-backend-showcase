/**
 * 场景 09：HTTP 客户端（超时 / 重试 / 熔断） — TS(Node) 实现
 *
 * Node HTTP Client 特点：
 * 1. undici = Node 生态事实标准（原生 fetch 底层用的就是 undici）
 * 2. undici 连接池：new Agent({ connections: 100, pipelining: 2 })
 * 3. 超时：requestOptions.timeout 整体超时 / agent.disconnect 控制
 * 4. 重试：p-retry / 手动实现
 * 5. 熔断：brakes / 手动实现
 *
 * 和其他语言对比：
 * - Node 原生 fetch() 底层就是 undici，所以用 undici 最贴近生产
 * - Node 单线程事件循环，IO 密集 HTTP client 效率极高
 * - 但 CPU 密集计算（重试中的 backoff 延迟）会阻塞事件循环
 */
import Fastify from 'fastify';
import { request, Agent, Pool, fetch as undiciFetch } from 'undici';

const PORT = 8119;
const MOCK_PORT = 8204;

// ==================== 内置 Mock Server ====================

import * as http from 'http';

function startMockServer() {
  const server = http.createServer((req, res) => {
    res.setHeader('Content-Type', 'application/json');
    const path = req.url || '/';

    if (path === '/ok') {
      res.writeHead(200);
      res.end(JSON.stringify({ ok: true, service: 'ts-node-mock' }));
    } else if (path === '/slow') {
      setTimeout(() => {
        res.writeHead(200);
        res.end(JSON.stringify({ ok: true, slow: true }));
      }, 2000);
    } else if (path === '/fail') {
      res.writeHead(500);
      res.end(JSON.stringify({ error: 'mock failure' }));
    } else {
      res.writeHead(404);
      res.end(JSON.stringify({ error: 'not found' }));
    }
  });

  server.listen(MOCK_PORT, () => {
    console.log(`[TS-Node MockServer] starting on http://localhost:${MOCK_PORT}`);
  });
}
startMockServer();

// ==================== 熔断（手动实现） ====================

class CircuitBreaker {
  private failureCount = 0;
  private state: 'closed' | 'open' | 'half-open' = 'closed';
  private lastFailureTime = 0;

  constructor(private threshold: number, private halfOpenAfterMs: number) {}

  allow(): boolean {
    if (this.state === 'open') {
      if (Date.now() - this.lastFailureTime >= this.halfOpenAfterMs) {
        this.state = 'half-open';
        return true;
      }
      return false;
    }
    return true;
  }

  recordSuccess(): void {
    this.failureCount = 0;
    this.state = 'closed';
  }

  recordFailure(): void {
    this.failureCount++;
    this.lastFailureTime = Date.now();
    if (this.failureCount >= this.threshold) {
      this.state = 'open';
    }
  }

  getState(): string {
    return this.state;
  }
}

const cb = new CircuitBreaker(3, 10_000);

// ==================== 类型定义 ====================

interface CallBody {
  url?: string;
  timeout_ms?: number;
  retry_times?: number;
}

interface CallResponse {
  success: boolean;
  status_code: number;
  latency_ms: number;
  retries: number;
  error?: string;
  body_preview?: any;
  url: string;
  timestamp: string;
}

// ==================== HTTP Client 核心 ====================

const fastify = Fastify({ logger: true });

// undici Pool：连接池（每个主机）
const pool = new Pool(`http://localhost:${MOCK_PORT}`, {
  connections: 100,
  pipelining: 2,
});

fastify.post<{ Body: CallBody }>('/call-external', async (request) => {
  const reqBody = request.body || {};
  const url = reqBody.url || `http://localhost:${MOCK_PORT}/ok`;
  const timeoutMs = reqBody.timeout_ms || 5000;
  const maxRetries = reqBody.retry_times || 2;

  const resp: CallResponse = {
    success: false,
    status_code: 0,
    latency_ms: 0,
    retries: 0,
    url,
    timestamp: new Date().toISOString(),
  };

  // 熔断检查
  if (!cb.allow()) {
    resp.error = 'CIRCUIT_OPEN: 熔断中';
    return resp;
  }

  const start = Date.now();
  const maxAttempts = maxRetries + 1;
  let lastError: string | undefined;

  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    // 指数退避
    if (attempt > 0) {
      const backoffMs = 100 * Math.pow(2, attempt - 1); // 100 → 200 → 400
      await new Promise(r => setTimeout(r, backoffMs));
    }

    console.log(`[HTTP-CLIENT] → GET ${url} (attempt ${attempt + 1})`);

    try {
      const { statusCode, body } = await request(url, {
        method: 'GET',
        headersTimeout: 3000,    // 连接超时
        bodyTimeout: timeoutMs,   // 读取超时（整个响应体）
        requestTimeout: timeoutMs + 1000, // 整体超时
      });

      const text = await body.text();
      let bodyPreview: any = text.slice(0, 200);
      try {
        bodyPreview = JSON.parse(text);
      } catch { /* 保持 string */ }

      // 5xx 重试
      if (statusCode >= 500 && attempt < maxRetries) {
        lastError = `HTTP ${statusCode}`;
        continue;
      }

      const latency = Date.now() - start;

      if (statusCode < 400) {
        cb.recordSuccess();
      }

      resp.success = statusCode < 400;
      resp.status_code = statusCode;
      resp.latency_ms = latency;
      resp.retries = attempt;
      resp.body_preview = bodyPreview;
      return resp;

    } catch (err: any) {
      lastError = err.message || String(err);
      if (attempt >= maxRetries - 1) {
        break;
      }
    }
  }

  // 全部失败
  cb.recordFailure();
  resp.success = false;
  resp.latency_ms = Date.now() - start;
  resp.retries = maxRetries;
  resp.error = lastError || 'unknown error';
  return resp;
});

fastify.get('/health', async () => ({
  service: 'http-client-ts-node',
  mock_port: MOCK_PORT,
  cb_state: cb.getState(),
}));

// ==================== 启动 ====================

const start = async () => {
  try {
    await fastify.listen({ port: PORT, host: '0.0.0.0' });
    console.log(`[TS-Node] http-client server starting on ${PORT}`);
  } catch (err) {
    fastify.log.error(err);
    process.exit(1);
  }
};

start();
