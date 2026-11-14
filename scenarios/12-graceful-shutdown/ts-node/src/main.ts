/**
 * 场景 12：优雅关闭 — TS(Node) 实现（Fastify）
 *
 * Node 优雅关闭特点：
 * 1. process.on('SIGTERM') / process.on('SIGINT') 捕获信号
 * 2. server.close() 停止接收新连接，等待 in-flight 请求完成
 * 3. 超时保护：setTimeout + process.exit(1) 强制关闭
 * 4. Node 单线程 → 不存在多线程竞争，状态更简单
 *
 * 和其他语言对比：
 * - Node 设计和 Go 类似（signal handler + close()）
 * - 优势：单线程天然无锁
 * - 坑：process.exit() 会立即杀死进程，超时保护必须有
 */
import Fastify from 'fastify';
import pino from 'pino';

const PORT = 8134;
const SHUTDOWN_TIMEOUT_MS = 10_000;

// pino 初始化：JSON 格式 + stdout + 最低 DEBUG 级别
const logger = pino({
  level: process.env.LOG_LEVEL || 'debug',
  timestamp: pino.stdTimeFunctions.isoTime,
  transport: { target: 'pino/file', options: { destination: 1 } }
});

// ==================== 全局状态 ====================

let inFlightCount = 0;
let shuttingDown = false;

// ==================== Fastify 服务 ====================

const fastify = Fastify({
  logger,
  // 注意：这里必须是 'idle'，不能写 true。
  // true 会在 close() 时**立即掐断所有连接**（含正在处理的请求），
  // 于是"等 in-flight 请求完成"直接失效 —— 客户端会收到 connection reset。
  // 'idle' 只关掉空闲的 keep-alive 连接，在途请求得以跑完。
  forceCloseConnections: 'idle',
});

fastify.get('/api/long-task', async () => {
  inFlightCount++;
  const id = inFlightCount;
  fastify.log.info({ msg: `[REQUEST] 开始处理 long-task, id=${id}, in-flight=${inFlightCount}` });

  // 模拟 3s 耗时
  await new Promise(resolve => setTimeout(resolve, 3000));

  inFlightCount--;
  fastify.log.info({ msg: `[REQUEST] 完成 long-task, id=${id}` });

  return {
    ok: true,
    duration_ms: 3000,
    shutting_down: shuttingDown,
  };
});

fastify.get('/api/health', async (_req, reply) => {
  const body = {
    service: 'graceful-shutdown-ts-node',
    shutting_down: shuttingDown,
    in_flight: inFlightCount,
  };

  // 必须用 reply.code()：Fastify 实例上并没有 code()/send() 方法
  // （写成 fastify.code(503).send(body) 会在关闭期间抛
  //  "app.code is not a function"，导致 readiness 探针拿到 500 而不是预期的 503）
  reply.code(shuttingDown ? 503 : 200);
  return body;
});

// ==================== 启动 ====================

const start = async () => {
  try {
    logger.info({ msg: 'graceful shutdown scene', timeoutMs: SHUTDOWN_TIMEOUT_MS });

    await fastify.listen({ port: PORT, host: '0.0.0.0' });
  } catch (err) {
    logger.error({ err }, 'server failed to start');
    process.exit(1);
  }
};

start();

// ==================== 优雅关闭信号处理 ====================

async function gracefulShutdown(signal: string) {
  logger.info({ msg: 'graceful shutdown: signal received', signal });
  logger.info({ msg: 'graceful shutdown: Step 1/4: mark shutting_down=true' });
  shuttingDown = true;

  logger.info({ msg: 'graceful shutdown: Step 2/4: stop accepting new requests' });
  logger.info({ msg: 'graceful shutdown: Step 3/4: waiting for in-flight requests', timeoutMs: SHUTDOWN_TIMEOUT_MS });

  // 超时强制关闭
  const forceExitTimer = setTimeout(() => {
    logger.warn({ msg: 'graceful shutdown: timeout, forcing exit' });
    process.exit(1);
  }, SHUTDOWN_TIMEOUT_MS);

  try {
    // fastify.close()：停止接收新请求 + 等待正在处理的请求完成
    await fastify.close();

    clearTimeout(forceExitTimer);
    logger.info({ msg: 'graceful shutdown: all requests completed' });
  } catch (err) {
    logger.error({ err }, 'graceful shutdown: close error');
    process.exit(1);
  }

  logger.info({ msg: 'graceful shutdown: Step 4/4: release resources' });
  logger.info({ msg: 'graceful shutdown complete' });
  process.exit(0);
}

// 注册信号处理器
process.on('SIGTERM', () => gracefulShutdown('SIGTERM'));
process.on('SIGINT', () => gracefulShutdown('SIGINT'));
