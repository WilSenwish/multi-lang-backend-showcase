/**
 * 场景 07：结构化日志 — TS(Node) 实现 (pino + fastify)
 *
 * Node 结构化日志特点：
 * 1. pino 是 Node 生态最快的 JSON 日志库（异步 + 零分配）
 * 2. fastify 内置 pino logger（server.logger.info() 直接用）
 * 3. pino-pretty（开发时用）和 pino-transport（生产时输出到 Loki/ELK）
 * 4. reqId 通过 fastify 的 request.id 自动生成，所有日志自动带上
 * 5. 错误栈：pino 会自动识别 Error 对象，输出 err.stack
 *
 * 和其他语言对比：
 * - pino 速度极快（Node 生态天花板）
 * - fastify 集成最方便，server.logger 自动绑定
 * - TS 类型安全 + pino 的 ChildLogger 子 logger 支持
 * - 但 Node 单线程，大日志量会阻塞事件循环（用 async transport 解）
 */
import Fastify from 'fastify';
import pino from 'pino';
import { randomUUID } from 'crypto';

const PORT = 8109;

// pino logger 配置：JSON 到 stdout
const logger = pino({
  name: 'structured-logging-ts-node',
  level: 'info',
  base: { app: 'structured-logging-ts-node' }, // 所有日志自动加 app 字段
  timestamp: pino.stdTimeFunctions.isoTime,    // ISO-8601 时间戳
});

const fastify = Fastify({
  // 自定义 logger 实例要通过 `logger` 传入：fastify v4 没有 loggerInstance 选项，
  // 传错键名会被静默忽略，服务退回 fastify 默认 logger（上面的 name/base/isoTime 全丢）
  logger,
  genReqId: () => randomUUID().substring(0, 8), // 请求 ID 生成
});

// ==================== 端点 ====================

/** 方法不匹配时返回 405（fastify 的 .get 默认给 404，与其余四门不一致） */
function methodGuard(request: any, reply: any, allow: string): boolean {
  if (request.method !== allow) {
    reply.code(405);
    return false;
  }
  return true;
}

fastify.all('/ping', async (request, reply) => {
  if (!methodGuard(request, reply, 'GET')) return { error: 'method not allowed' };
  const start = Date.now();
  const reqId = request.id as string;

  // fastify 的 request.log 是带 requestId 的子 logger；userId 显式带上，
  // 与其余四门的链路字段保持一致
  request.log.info({ msg: 'ping request handled', userId: 'anonymous', path: '/ping' });
  request.log.info({ msg: 'request completed', costMs: Date.now() - start, userId: 'anonymous', path: '/ping' });

  return { pong: true, request_id: reqId };
});

fastify.all('/debug', async (request, reply) => {
  if (!methodGuard(request, reply, 'GET')) return { error: 'method not allowed' };
  // 级别与消息与其余四门对齐：INFO "debug endpoint hit"（pino 的 info 默认级别不开 debug）
  request.log.info({ msg: 'debug endpoint hit', userId: 'debug-user', path: '/debug' });
  return { debug: true, request_id: request.id };
});

fastify.all('/error', async (request, reply) => {
  if (!methodGuard(request, reply, 'GET')) return { error: 'method not allowed' };
  try {
    // 故意模拟错误
    const nullStr: string | null = null;
    nullStr!.split(','); // TypeError!
  } catch (err: any) {
    // pino 的 error 方法自动识别 Error 对象，输出 err.stack
    request.log.error({
      msg: 'request failed with exception',
      costMs: 150,
      errorCode: 'NULL_POINTER',
      userId: 'error-user',
      path: '/error',
      err, // pino 会自动解析 Error，输出 type/message/stack
    });
  }

  return { error: 'simulated' };
});

fastify.all('/bench', async (request, reply) => {
  if (!methodGuard(request, reply, 'GET')) return { error: 'method not allowed' };
  const raw = (request.query as { count?: string }).count;
  // count 缺省 1000；非数字 / < 1 都是客户端错误 → 400
  // （之前 parseInt('abc') 得到 NaN，循环不执行、avgLogNs 变成 NaN→null 蒙混过关）
  let count = 1000;
  if (raw !== undefined) {
    const n = Number(raw);
    if (!Number.isInteger(n) || n < 1) {
      reply.code(400);
      return { error: 'count must be an integer >= 1' };
    }
    count = n;
  }

  const start = Date.now();
  for (let i = 0; i < count; i++) {
    request.log.info({ msg: 'benchmark log entry', index: i, total: count, userId: 'bench-user', path: '/bench' });
  }
  const cost = Date.now() - start;
  const avgNs = (cost * 1_000_000) / count;

  request.log.info({
    msg: 'benchmark completed',
    count,
    totalCostMs: cost,
    avgLogNs: Math.round(avgNs),
    userId: 'bench-user',
    path: '/bench',
  });

  return {
    count,
    total_cost_ms: cost,
    avg_log_ns: Math.round(avgNs),
    request_id: request.id,
  };
});

// ==================== 启动 ====================

const start = async () => {
  try {
    await fastify.listen({ port: PORT, host: '0.0.0.0' });
    logger.info({ msg: 'server starting', addr: `0.0.0.0:${PORT}`, mode: 'prod' });
  } catch (err) {
    logger.error({ err, msg: 'server failed to start' });
    process.exit(1);
  }
};

start();
