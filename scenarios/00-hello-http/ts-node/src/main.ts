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

// GET /hello
fastify.get<{ Querystring: { name?: string } }>(
  '/hello',
  {
    schema: {
      querystring: z.object({
        name: z.string().optional(),
      }).parse,
      response: {
        200: z.object({
          msg: z.string(),
        }).parse,
      },
    },
  },
  async (request, reply): Promise<HelloResponse> => {
    const name = request.query.name?.trim() || DEFAULT_NAME;
    return { msg: `hello ${name}` };
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
