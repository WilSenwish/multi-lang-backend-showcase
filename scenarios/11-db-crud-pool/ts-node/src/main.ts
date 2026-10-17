/**
 * 场景 11：数据库 CRUD + 连接池 — TS(Node) 实现
 *
 * Node DB 特点：
 * 1. better-sqlite3：同步 SQLite 驱动（Node 单线程，同步高效）
 * 2. Node 单线程 → 连接池概念弱化（单进程 SQLite 文件锁足够）
 * 3. 可以用 Prisma（类型安全 ORM），但 better-sqlite3 更轻量
 * 4. 原生 TS 类型定义实体
 *
 * 和其他语言对比：
 * - Node 单线程 + better-sqlite3 同步 → 不需要连接池！
 * - 这是 Node 的特殊点（单线程天然避免多连接竞争）
 * - Prisma 可以生成 TS 类型，但 better-sqlite3 原生就支持
 */
import Fastify from 'fastify';
import Database from 'better-sqlite3';

const PORT = 8129;

// ==================== DB 初始化 ====================

const db = new Database('./demo_ts.db');

// SQLite 性能调优
db.pragma('journal_mode = WAL');      // WAL 模式，提升读写并发
db.pragma('synchronous = NORMAL');     // 平衡性能和安全

// 自动建表
db.exec(`
  CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT,
    age INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
  )
`);

console.log('[TS-Node] DB 初始化成功（SQLite: demo_ts.db）');

// ==================== 类型定义 ====================

interface User {
  id: number;
  name: string;
  email: string | null;
  age: number | null;
  created_at: string | null;
}

// ==================== Fastify 服务 ====================

const fastify = Fastify({ logger: true });

// CREATE
fastify.post('/users', async (request, reply) => {
  const body = request.body as { name?: string; email?: string | null; age?: number | null };
  if (body == null || body.name == null) {
    reply.code(400).send({ error: 'name is required' });
    return;
  }

  const stmt = db.prepare('INSERT INTO users (name, email, age) VALUES (?, ?, ?)');
  const info = stmt.run(body.name, body.email ?? null, body.age ?? null);

  // 查询刚插入的
  const user = db.prepare('SELECT * FROM users WHERE id = ?').get(info.lastInsertRowid as number);
  reply.code(201).send(user);
});

// READ ONE
fastify.get('/users/:id', async (request, reply) => {
  const { id } = request.params as { id: string };
  const user = db.prepare('SELECT * FROM users WHERE id = ?').get(Number(id));

  if (!user) {
    reply.code(404).send({ error: 'not found' });
    return;
  }
  reply.send(user);
});

// LIST (分页)
fastify.get('/users', async (request, reply) => {
  const { page = 0, size = 10 } = request.query as { page?: string; size?: string };
  const pageNum = Number(page);
  const sizeNum = Number(size);

  if (!Number.isInteger(pageNum) || !Number.isInteger(sizeNum) || pageNum < 0 || sizeNum <= 0) {
    reply.code(400).send({ error: 'invalid pagination' });
    return;
  }

  const total = (db.prepare('SELECT COUNT(*) as count FROM users').get() as { count: number }).count;
  const items = db.prepare('SELECT * FROM users ORDER BY id ASC LIMIT ? OFFSET ?').all(sizeNum, pageNum * sizeNum);

  return { items, total, page: pageNum, size: sizeNum };
});

// UPDATE
fastify.put('/users/:id', async (request, reply) => {
  const { id } = request.params as { id: string };
  const body = request.body as Partial<User>;

  // 查存在性
  const exists = db.prepare('SELECT id FROM users WHERE id = ?').get(Number(id));
  if (!exists) {
    reply.code(404).send({ error: 'not found' });
    return;
  }

  // 动态 SET 子句
  const fields: string[] = [];
  const values: any[] = [];

  if (body.name !== undefined) { fields.push('name = ?'); values.push(body.name); }
  if (body.email !== undefined) { fields.push('email = ?'); values.push(body.email); }
  if (body.age !== undefined) { fields.push('age = ?'); values.push(body.age); }

  if (fields.length > 0) {
    const sql = `UPDATE users SET ${fields.join(', ')} WHERE id = ?`;
    values.push(Number(id));
    db.prepare(sql).run(...values);
  }

  // 返回更新后
  const user = db.prepare('SELECT * FROM users WHERE id = ?').get(Number(id));
  reply.send(user);
});

// DELETE
fastify.delete('/users/:id', async (request, reply) => {
  const { id } = request.params as { id: string };
  const info = db.prepare('DELETE FROM users WHERE id = ?').run(Number(id));

  if (info.changes === 0) {
    reply.code(404).send({ error: 'not found' });
    return;
  }
  reply.code(204).send();
});

// HEALTH
fastify.get('/health', async () => ({
  service: 'db-crud-pool-ts-node',
  db: 'sqlite (better-sqlite3)',
}));

// ==================== 启动 ====================

const start = async () => {
  try {
    await fastify.listen({ port: PORT, host: '0.0.0.0' });
    console.log(`[TS-Node] db-crud-pool server starting on ${PORT}`);
  } catch (err) {
    fastify.log.error(err);
    process.exit(1);
  }
};

start();
