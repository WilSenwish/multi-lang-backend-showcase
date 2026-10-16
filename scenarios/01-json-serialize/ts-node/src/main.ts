/**
 * 场景 01：JSON 序列化/反序列化 — TypeScript Node 实现 (fastify + 原生 JSON)
 *
 * TS/Node JSON 特点（和其他 4 门语言对比）：
 * 1. 原生 JSON.stringify / JSON.parse 是运行时，无类型安全
 * 2. TypeScript 编译期有类型，但 JSON.stringify 不认 TS 类型（类型擦除）
 * 3. null 和 undefined 在 JSON.stringify 中行为不同：
 *    - 对象中 null 保留：{a: null} → {"a": null}
 *    - 对象中 undefined 跳过：{a: undefined} → {}
 *    - 数组中两者都保留：[1, null, undefined] → [1, null, null]
 * 4. 空数组 [] → JSON []（和所有语言一致）
 * 5. 无额外库，原生就支持，性能极高
 *
 * 和 Java Jackson / Rust serde 的关键差异：
 * - Java/Rust 字段级注解控制，TS 靠 JSON.stringify 原生行为
 * - Java Jackson null 默认输出，TS null 也输出 — 但 undefined 跳过
 * - Rust Option::None 显式表达，TS undefined 隐式存在
 */
import Fastify from 'fastify';

const PORT = 8094;

// 演示用的 demo 对象（注意 TS 里 null vs undefined 的差异）
function demoUser() {
  return {
    id: 1,
    name: 'Alice',
    email: null,        // null → JSON "email": null（保留）
    age: 28,
    tags: ['engineer', 'java'],
    address: {
      city: 'Beijing',
      zip: '100000',
    },
    scores: [] as number[], // 空数组 → JSON "scores": []
  };
}

interface DeserializeBody {
  json_string: string;
}

const fastify = Fastify({ logger: true });

// GET /demo — 返回标准测试对象
fastify.get('/demo', async () => {
  return demoUser();
});

// POST /serialize — 对象 → JSON 字符串
fastify.post('/serialize', async (request, reply) => {
  const body = request.body as Record<string, unknown>;

  const start = performance.now();
  const jsonStr = JSON.stringify(body);
  const elapsedUs = Math.round((performance.now() - start) * 1000);

  const pretty = JSON.stringify(body, null, 2);

  return {
    json: jsonStr,
    bytes: Buffer.byteLength(jsonStr),
    time_us: elapsedUs,
    pretty: pretty,
  };
});

// POST /deserialize — JSON 字符串 → 对象
// size 的契约口径是 UTF-8 字节数（Buffer.byteLength）；TS 的 string.length 是
// UTF-16 代码单元数，含非 ASCII 时与另外四门语言不一致。
fastify.post<{ Body: DeserializeBody }>('/deserialize', async (request, reply) => {
  const { json_string } = request.body;

  const start = performance.now();
  const parsed = JSON.parse(json_string);
  const elapsedUs = Math.round((performance.now() - start) * 1000);

  return {
    parsed: parsed,
    time_us: elapsedUs,
    size: Buffer.byteLength(json_string),
  };
});

// POST /roundtrip — 往返保真测试
fastify.post('/roundtrip', async (request, reply) => {
  const body = request.body as Record<string, unknown>;

  const json1 = JSON.stringify(body);
  const parsed = JSON.parse(json1);
  const json2 = JSON.stringify(parsed);

  return {
    original_json: json1,
    roundtrip_json: json2,
    equal: json1 === json2,
    original_bytes: Buffer.byteLength(json1),
    roundtrip_bytes: Buffer.byteLength(json2),
  };
});

// GET /bench — 10000 次性能基准
fastify.get('/bench', async () => {
  const user = demoUser();
  const iterations = 10000;

  // 预热
  for (let i = 0; i < 100; i++) {
    const s = JSON.stringify(user);
    JSON.parse(s);
  }

  const start = performance.now();
  let lastJson = '';
  for (let i = 0; i < iterations; i++) {
    lastJson = JSON.stringify(user);
    JSON.parse(lastJson);
  }
  const totalMs = Math.round(performance.now() - start);

  return {
    language: 'ts-node/JSON',
    iterations: iterations,
    total_time_ms: totalMs,
    avg_time_us: Math.round((totalMs * 1000 / iterations) * 100) / 100,
    json_size_bytes: Buffer.byteLength(lastJson),
  };
});

const startServer = async () => {
  try {
    await fastify.listen({ port: PORT, host: '0.0.0.0' });
    fastify.log.info(`[TS-Node] json-serialize server listening on ${PORT}`);
  } catch (err) {
    fastify.log.error(err);
    process.exit(1);
  }
};

startServer();
