/**
 * scenarios/00-hello-http TypeScript Node 实现 (fastify + zod)
 *
 * 统一 API 契约:
 *   GET /hello?name={xxx}
 *   → {"msg": "hello {xxx}"}
 *   → {"msg": "hello world"}  // name 缺省
 */
import Fastify from 'fastify';
import pino from 'pino';
import { z } from 'zod';

const DEFAULT_NAME = 'world';
const PORT = 8084;

// pino 初始化：JSON 格式 + stdout + 最低 DEBUG 级别
const logger = pino({
  level: process.env.LOG_LEVEL || 'debug',
  timestamp: pino.stdTimeFunctions.isoTime,
  transport: { target: 'pino/file', options: { destination: 1 } }
});

// 响应 DTO 类型
interface HelloResponse {
  msg: string;
}

const fastify = Fastify({
  logger,
});

// zod 用于运行时校验（fastify 的 schema 字段需为 JSON Schema，不能传 zod.parse 函数）
const nameSchema = z.string().trim().max(64);

// GET /hello
// 注意用 fastify.all 而不是 fastify.get：fastify 对"路径匹配但方法不匹配"默认返回 404，
// 而另外四门语言（Spring/net-http/FastAPI/axum）都返回 405 —— 这是 fastify 的已知差异，
// 这里显式抹平，让五门语言的 HTTP 语义一致（契约：非 GET → 405）。
fastify.all<{ Querystring: { name?: string } }>(
  '/hello',
  {
    schema: {
      querystring: {
        type: 'object',
        properties: { name: { type: 'string' } },
        additionalProperties: true,
      },
      response: {
        200: {
          type: 'object',
          properties: { msg: { type: 'string' } },
          required: ['msg'],
        },
      },
    },
  },
  async (request, reply): Promise<HelloResponse> => {
    if (request.method !== 'GET') {
      reply.code(405);
      return { msg: 'method not allowed' };
    }
    const raw = request.query.name;
    const name = raw ? nameSchema.parse(raw) : DEFAULT_NAME;
    return { msg: `hello ${name || DEFAULT_NAME}` };
  },
);

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
