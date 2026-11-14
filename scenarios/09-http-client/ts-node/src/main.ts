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
import pino from 'pino';
// ⚠️ 必须起别名：路由处理器形参名叫 request（fastify 约定），
// 直接 import { request } 会被形参遮蔽，调用时抛 "request2 is not a function"，
// 于是每个 /call-external 都瞬间失败 —— 老代码全量请求 100% 报错，
// 而"端口监听级"验证根本发现不了（服务是正常起来的）。
import { request as undiciRequest, Agent, Pool, fetch as undiciFetch } from 'undici';

const PORT = 8119;
const MOCK_PORT = 8204;

// pino 初始化：JSON 格式 + stdout + 最低 DEBUG 级别
const logger = pino({
  level: process.env.LOG_LEVEL || 'debug',
  timestamp: pino.stdTimeFunctions.isoTime,
  transport: { target: 'pino/file', options: { destination: 1 } }
});

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
    logger.info({ msg: 'mock server starting', mockPort: MOCK_PORT });
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

// undici 对连接拒绝等错误抛的是 AggregateError（message 为空），
// 直接取 err.message 只能拿到 "AggregateError" —— 展平出内层原因才有诊断价值。
function describeError(err: any): string {
  if (err instanceof AggregateError && Array.isArray((err as any).errors)) {
    const inner = (err as any).errors.map((e: any) => e?.message || String(e)).join('; ');
    if (inner) return inner;
  }
  return err?.cause?.message || err?.message || String(err);
}

const fastify = Fastify({ logger });

// undici Pool：连接池（每个主机）
const pool = new Pool(`http://localhost:${MOCK_PORT}`, {
  connections: 100,
  pipelining: 2,
});

fastify.post<{ Body: CallBody }>('/call-external', async (request) => {
  const reqBody = request.body || {};
  // 显式 undefined 检查而不是 ||：timeout_ms=0 / retry_times=0 是合法值，
  // || 会把"显式 0"吞成默认值（其他四门语言都接受 0）。
  const url = reqBody.url ?? `http://localhost:${MOCK_PORT}/ok`;
  const timeoutMs = reqBody.timeout_ms ?? 5000;
  const maxRetries = reqBody.retry_times ?? 2;

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

    logger.debug({ url, attempt: attempt + 1 }, 'GET request');

    try {
      // undici 自带的 headersTimeout/bodyTimeout 走"快定时器"（RESOLUTION_MS=1000，
      // 每 ~499ms 才 tick 一次，官方定位是"1 秒以上的粗粒度定时器"）——
      // 传 500ms 实测要 ~1000ms 才触发，比请求级 deadline 还慢。
      // 因此 deadline 用 AbortSignal 精确控制（与 Go 的 context 超时、
      // Rust 的 .timeout() 语义一致：整个请求的总时限）。
      const controller = new AbortController();
      const deadline = setTimeout(() => controller.abort(), timeoutMs);
      try {
        const { statusCode, body } = await undiciRequest(url, {
          method: 'GET',
          signal: controller.signal,
        });

        const text = await body.text();
        let bodyPreview: any = text.slice(0, 200);
        try {
          bodyPreview = JSON.parse(text);
        } catch { /* 保持 string */ }

        // 5xx 重试；最后一次也失败时按"重试耗尽"语义返回真实状态码
        // （README 统一接口：重试 2 次后 status_code=500），并记熔断失败 ——
        // 老代码在 5xx 终局既不设 error 也不记失败，熔断器永远打不开。
        if (statusCode >= 500) {
          lastError = `HTTP ${statusCode}`;
          if (attempt < maxRetries) continue;
          cb.recordFailure();
          resp.success = false;
          resp.status_code = statusCode;
          resp.latency_ms = Date.now() - start;
          resp.retries = attempt;
          resp.error = lastError;
          return resp;
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
      } finally {
        clearTimeout(deadline);
      }

    } catch (err: any) {
      lastError = describeError(err);
      // 只在"最后一次尝试"退出：老代码写 attempt >= maxRetries - 1，
      // retry_times=1 时第一次失败就 break，实际只发了 1 次请求却报告 retries=1。
      if (attempt >= maxAttempts - 1) {
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
    logger.info({ msg: 'server starting', addr: `0.0.0.0:${PORT}` });
  } catch (err) {
    logger.error({ err }, 'server failed to start');
    process.exit(1);
  }
};

start();
