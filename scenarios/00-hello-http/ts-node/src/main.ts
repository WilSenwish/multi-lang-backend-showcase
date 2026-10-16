/**
 * scenarios/00-hello-http TypeScript Node 实现 (fastify + zod)
 *
 * 统一 API 契约:
 *   GET /hello?name={xxx}
 *   → {"msg": "hello {xxx}"}
 *   → {"msg": "hello world"}  // name 缺省
 */
import Fastify from 'fastify';
import { z } from 'zod';

const DEFAULT_NAME = 'world';
const PORT = 8084;

// 响应 DTO 类型
interface HelloResponse {
  msg: string;
}

const fastify = Fastify({
  logger: true,
});

// zod 用于运行时校验（fastify 的 schema 字段需为 JSON Schema，不能传 zod.parse 函数）
const nameSchema = z.string().trim().max(64);

// GET /hello
fastify.get<{ Querystring: { name?: string } }>(
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
    const raw = request.query.name;
    const name = raw ? nameSchema.parse(raw) : DEFAULT_NAME;
    return { msg: `hello ${name || DEFAULT_NAME}` };
  },
);

const start = async () => {
  try {
    await fastify.listen({ port: PORT, host: '0.0.0.0' });
    fastify.log.info(`[TS-Node] hello-http server listening on ${PORT}`);
  } catch (err) {
    fastify.log.error(err);
    process.exit(1);
  }
};

start();
