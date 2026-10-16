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

const PORT = 8134;
const SHUTDOWN_TIMEOUT_MS = 10_000;

// ==================== 全局状态 ====================

let inFlightCount = 0;
let shuttingDown = false;

// ==================== Fastify 服务 ====================

const fastify = Fastify({
  logger: true,
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
    console.log('========================================');
    console.log('场景 12：优雅关闭 — Node 实现（Fastify）');
    console.log(`信号：kill -TERM <pid> 或 Ctrl+C（超时 ${SHUTDOWN_TIMEOUT_MS}ms）`);
    console.log('========================================');

    await fastify.listen({ port: PORT, host: '0.0.0.0' });
  } catch (err) {
    fastify.log.error(err);
    process.exit(1);
  }
};

start();

// ==================== 优雅关闭信号处理 ====================

async function gracefulShutdown(signal: string) {
  console.log('========================================');
  console.log(`[GRACEFUL SHUTDOWN] 收到信号: ${signal}`);
  console.log('[GRACEFUL SHUTDOWN] Step 1/4: 标记 shutting_down=true');
  shuttingDown = true;

  console.log('[GRACEFUL SHUTDOWN] Step 2/4: 停止接收新请求');

  console.log(`[GRACEFUL SHUTDOWN] Step 3/4: 等待 in-flight 请求完成 (timeout=${SHUTDOWN_TIMEOUT_MS}ms)`);

  // 超时强制关闭
  const forceExitTimer = setTimeout(() => {
    console.log('[GRACEFUL SHUTDOWN] ⚠️ 超时！强制退出');
    process.exit(1);
  }, SHUTDOWN_TIMEOUT_MS);

  try {
    // fastify.close()：停止接收新请求 + 等待正在处理的请求完成
    await fastify.close();

    clearTimeout(forceExitTimer);
    console.log('[GRACEFUL SHUTDOWN] ✅ 所有请求完成');
  } catch (err) {
    fastify.log.error({ msg: '[GRACEFUL SHUTDOWN] close error', err });
    process.exit(1);
  }

  console.log('[GRACEFUL SHUTDOWN] Step 4/4: 释放资源');
  console.log('[GRACEFUL SHUTDOWN] ✅ Shutdown complete');
  console.log('========================================');
  process.exit(0);
}

// 注册信号处理器
process.on('SIGTERM', () => gracefulShutdown('SIGTERM'));
process.on('SIGINT', () => gracefulShutdown('SIGINT'));
