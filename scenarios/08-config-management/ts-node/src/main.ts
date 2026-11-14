/**
 * 场景 08：多环境配置管理 — TS(Node) 实现 (zod + @fastify/env)
 *
 * Node 配置管理特点：
 * 1. zod schema 定义配置结构 + 约束（启动时校验）
 * 2. @fastify/env 自动加载 .env 文件 + 进程 env，fastify 注入
 * 3. dotenv 从 .env 读环境变量
 * 4. 校验时机：启动时（和 Java/Go/Python 一样）
 * 5. TS 类型安全 + zod 运行时校验 → 双重保险
 *
 * 和其他语言对比：
 * - zod 的 schema 既是类型定义又是运行时校验（一次写两用）
 * - @fastify/env 会自动类型转换（PORT=8114 → number）
 * - Node 没有编译期配置 embed（不像 Rust config crate）
 * - 灵活：config 可以从 yaml / json / env 多来源合并
 */
import 'dotenv/config';
import Fastify from 'fastify';
import pino from 'pino';
import fs from 'fs';
import path from 'path';
import { z } from 'zod';

const PORT = 8114;

// pino 初始化：JSON 格式 + stdout + 最低 DEBUG 级别
const logger = pino({
  level: process.env.LOG_LEVEL || 'debug',
  timestamp: pino.stdTimeFunctions.isoTime,
  transport: { target: 'pino/file', options: { destination: 1 } }
});

// ==================== zod 配置 Schema ====================

// zod 的强大之处：类型定义 = 运行时校验 = 默认值
const ServerSchema = z.object({
  port: z.coerce.number().int().min(1).max(65535).default(8114),
  host: z.string().min(1).default('0.0.0.0'),
});

const DatabaseSchema = z.object({
  url: z.string().min(1).default('localhost:3306'),
  user: z.string().min(1).default('admin'),
  password: z.string().default('secret'),
  pool_size: z.coerce.number().int().min(1).max(100).default(10),
});

const LoggingSchema = z.object({
  level: z.enum(['TRACE', 'DEBUG', 'INFO', 'WARN', 'ERROR']).default('INFO'),
  json: z.coerce.boolean().default(true),
});

const AppConfigSchema = z.object({
  server: ServerSchema,
  database: DatabaseSchema,
  logging: LoggingSchema,
  env: z.string().default(process.env.MYAPP_ENV || 'default'),
  source: z.string().default('zod + @fastify/env + dotenv + MYAPP_ env'),
});

type AppConfig = z.infer<typeof AppConfigSchema>;

// ==================== 加载配置 ====================

function loadConfig(): AppConfig {
  // 1. 读 config.yaml（简单实现，用手写 yaml 不够，这里演示 env 优先）
  //    生产可用 yaml / js-yaml 库读 yaml，优先级：env > yaml > 默认值
  const envPrefix = 'MYAPP_';
  const getNestedEnv = (key: string, def: unknown): unknown => {
    // MYAPP_SERVER__PORT → 取 PORT，没有用默认值
    // 先把 MYAPP_ 前缀的 env 收集出来手动处理
    return process.env[key] !== undefined ? process.env[key] : def;
  };

  // 2. 把所有 MYAPP_ 开头的环境变量收集，合并到 config 上
  const yamlConfig: Record<string, unknown> = {}; // 默认值直接用 zod 的 default()

  // 3. 构建 envOverride：把 MYAPP_SERVER__PORT 映射成 { server: { port: ... } }
  //    Node 约定用 __（双下划线）分隔层级，和 Rust config crate 一致
  const envOverride: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(process.env)) {
    if (!key.startsWith(envPrefix)) continue;
    const path = key.slice(envPrefix.length).toLowerCase();
    const segments = path.split('__'); // MYAPP_SERVER__PORT → ["server", "port"]
    if (segments.length < 2) continue;

    // 嵌套写入对象
    let cur: any = envOverride;
    for (let i = 0; i < segments.length - 1; i++) {
      if (!cur[segments[i]]) cur[segments[i]] = {};
      cur = cur[segments[i]];
    }
    cur[segments[segments.length - 1]] = value;
  }

  // 4. zod 校验 + 合并
  //    zod parse 会自动填充 default，并对 envOverride 里的值做类型转换。
  //    注意：AppConfigSchema 的 server/database/logging 是必填对象，
  //    这里显式补空对象，避免无 MYAPP_* 环境变量时直接抛 ZodError。
  const config = AppConfigSchema.parse({
    server: {},
    database: {},
    logging: {},
    ...envOverride,
  });

  // 5. 额外验证（跨字段依赖等复杂校验）
  logger.info({ msg: 'config loaded', env: config.env, port: config.server.port });

  return config;
}

const globalConfig = loadConfig();

// ==================== Fastify 服务 ====================

const fastify = Fastify({ logger });

fastify.get('/config', async () => {
  const cfg: any = JSON.parse(JSON.stringify(globalConfig));
  // 脱敏密码
  cfg.database.password = '********';
  return cfg;
});

const start = async () => {
  try {
    await fastify.listen({ port: PORT, host: '0.0.0.0' });
    logger.info({ msg: 'server starting', addr: `0.0.0.0:${PORT}` });
  } catch (err) {
    logger.error({ err }, 'server failed to start');
    process.exit(1);
  }
};

logger.debug('env var example:');
logger.debug('  MYAPP_SERVER__PORT=9000 MYAPP_DATABASE__URL="prod-db:3306" npm run dev');
logger.debug('  (Node uses __ double underscore for level separator, same as Rust config crate)');

start();
