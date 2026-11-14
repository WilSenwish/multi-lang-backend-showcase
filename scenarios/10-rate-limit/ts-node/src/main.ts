/**
 * 场景 10：单机内存限流 — TS(Node) 实现（Fastify + 手写令牌桶）
 *
 * Node 限流特点：
 * 1. Node 单线程事件循环 → 天然无并发竞争（不需要锁！和 Python asyncio 一样）
 * 2. 用 process.hrtime() 精确计时
 * 3. rate-limiter-flexible 库支持多种算法，但手写更直观
 * 4. Node 单线程 CPU 密集计算会阻塞事件循环（令牌桶计算没问题，很轻）
 */
import Fastify from 'fastify';
import pino from 'pino';

const PORT = 8124;

// pino 初始化：JSON 格式 + stdout + 最低 DEBUG 级别
const logger = pino({
  level: process.env.LOG_LEVEL || 'debug',
  timestamp: pino.stdTimeFunctions.isoTime,
  transport: { target: 'pino/file', options: { destination: 1 } }
});

// ==================== 令牌桶 ====================

class TokenBucket {
  private tokens: number;
  private lastRefill: number; // nanoseconds via process.hrtime.bigint()
  private total = 0;
  private allowed = 0;
  private rejected = 0;

  constructor(
    private qps: number,
    private burst: number,
  ) {
    this.tokens = burst;
    this.lastRefill = Number(process.hrtime.bigint()) / 1e9; // 秒
  }

  private refill(): void {
    const now = Number(process.hrtime.bigint()) / 1e9;
    const elapsed = now - this.lastRefill;
    this.tokens = Math.min(this.burst, this.tokens + elapsed * this.qps);
    this.lastRefill = now;
  }

  tryAcquire(): boolean {
    this.refill();
    this.total++;
    if (this.tokens >= 1.0) {
      this.tokens -= 1.0;
      this.allowed++;
      return true;
    }
    this.rejected++;
    return false;
  }

  retryAfterMs(): number {
    this.refill();
    const deficit = 1.0 - this.tokens;
    if (deficit <= 0) return 0;
    return Math.round((deficit / this.qps) * 1000);
  }

  getStats() {
    return {
      total: this.total,
      allowed: this.allowed,
      rejected: this.rejected,
    };
  }
}

// 单例（Node 单线程，不需要加锁！）
const bucket = new TokenBucket(1.0, 10);

// ==================== Fastify 服务 ====================

const fastify = Fastify({ logger });

fastify.get('/api/heavy', async (_request, reply) => {
  if (!bucket.tryAcquire()) {
    const retryMs = bucket.retryAfterMs();
    const stats = bucket.getStats();

    fastify.log.warn({ msg: '[RateLimit] 429 被限流', retryAfterMs: retryMs });

    return reply.code(429).header('Retry-After', String(Math.max(1, Math.floor(retryMs / 1000) + 1))).send({
      error: 'rate limit exceeded',
      retry_after_ms: retryMs,
      ...stats,
    });
  }

  const stats = bucket.getStats();
  fastify.log.info({ msg: '[RateLimit] 200 通过' });

  return reply.send({
    ok: true,
    endpoint: '/api/heavy',
    ...stats,
  });
});

fastify.get('/health', async () => ({
  service: 'rate-limit-ts-node',
  algorithm: 'token-bucket (Node single-thread, no lock)',
  qps: 1.0,
  burst: 10,
  ...bucket.getStats(),
}));

// ==================== 启动 ====================

const start = async () => {
  try {
    logger.debug({ msg: 'rate limit config', qps: 1, burst: 10 });
    await fastify.listen({ port: PORT, host: '0.0.0.0' });
  } catch (err) {
    logger.error({ err }, 'server failed to start');
    process.exit(1);
  }
};

start();
