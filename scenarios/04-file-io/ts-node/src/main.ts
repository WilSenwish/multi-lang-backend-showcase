/**
 * 场景 04：文件读写 & 目录遍历 — TS(Node) 实现 (fastify + fs/promises)
 *
 * Node 文件 IO 特点：
 * 1. fs/promises 是原生异步 API（Node 14+）
 * 2. path 模块处理路径
 * 3. fs.readdirSync / glob 实现递归遍历（原生 readdir 只一层）
 * 4. fs.mkdirSync recursive:true 自动创建父目录
 * 5. Node 的 fs 底层用 libuv 异步线程池
 *
 * 和 Java NIO.2 / Rust tokio::fs 对比：
 * - Node fs/promises 是 async/await 风格，和 TS async 无缝配合
 * - 递归遍历需要自己写或用第三方库（Node 原生没有 walk）
 */
import Fastify from 'fastify';
import * as fs from 'fs/promises';
import * as path from 'path';

const PORT = 8099;

interface WriteBody {
  path: string;
  content: unknown;
  append?: boolean;
}

function contentToString(c: unknown): string {
  if (typeof c === 'string') return c;
  return JSON.stringify(c);
}

/** 递归遍历目录，统计文件数和总大小 */
async function walkDir(dirPath: string): Promise<{ files: number; totalBytes: number }> {
  let files = 0;
  let totalBytes = 0;

  async function walk(cur: string) {
    let entries: fs.Dirent[];
    try {
      entries = await fs.readdir(cur, { withFileTypes: true });
    } catch {
      return; // 忽略权限错误
    }
    for (const entry of entries) {
      const full = path.join(cur, entry.name);
      try {
        if (entry.isDirectory()) {
          await walk(full);
        } else if (entry.isFile()) {
          const stat = await fs.stat(full);
          files++;
          totalBytes += stat.size;
        }
      } catch {
        // 忽略
      }
    }
  }

  await walk(dirPath);
  return { files, totalBytes };
}

const fastify = Fastify({ logger: true });

// POST /file/write
fastify.post<{ Body: WriteBody }>('/file/write', async (request, reply) => {
  const { path: filePath, content, append = false } = request.body;

  try {
    // 确保父目录存在
    const dir = path.dirname(filePath);
    if (dir && dir !== '.') {
      await fs.mkdir(dir, { recursive: true });
    }

    const strContent = contentToString(content);

    if (append) {
      await fs.writeFile(filePath, strContent, { flag: 'a' });
    } else {
      await fs.writeFile(filePath, strContent, 'utf-8');
    }

    return {
      success: true,
      path: filePath,
      bytes_written: Buffer.byteLength(strContent),
      append,
    };
  } catch (err: any) {
    return { success: false, error: err.message };
  }
});

// GET /file/read
fastify.get('/file/read', async (request, reply) => {
  const { path: filePath } = request.query as { path: string };

  try {
    const stat = await fs.stat(filePath);
    if (!stat.isFile()) {
      reply.code(400);
      return { error: `不是文件: ${filePath}` };
    }

    const content = await fs.readFile(filePath, 'utf-8');
    return {
      path: filePath,
      content,
      bytes: Buffer.byteLength(content),
    };
  } catch (err: any) {
    if (err.code === 'ENOENT') {
      reply.code(404);
      return { error: `文件不存在: ${filePath}` };
    }
    reply.code(500);
    return { error: err.message };
  }
});

// GET /file/scan
fastify.get('/file/scan', async (request, reply) => {
  const { dir, recursive = 'true' } = request.query as { dir: string; recursive?: string };
  const isRecursive = recursive !== 'false';

  try {
    const stat = await fs.stat(dir);
    if (!stat.isDirectory()) {
      reply.code(400);
      return { error: `不是目录: ${dir}` };
    }

    let files = 0;
    let totalBytes = 0;

    if (isRecursive) {
      const result = await walkDir(dir);
      files = result.files;
      totalBytes = result.totalBytes;
    } else {
      const entries = await fs.readdir(dir, { withFileTypes: true });
      for (const entry of entries) {
        if (entry.isFile()) {
          const s = await fs.stat(path.join(dir, entry.name));
          files++;
          totalBytes += s.size;
        }
      }
    }

    return {
      dir,
      recursive: isRecursive,
      files,
      total_bytes: totalBytes,
    };
  } catch (err: any) {
    if (err.code === 'ENOENT') {
      reply.code(404);
      return { error: `目录不存在: ${dir}` };
    }
    reply.code(500);
    return { error: err.message };
  }
});

const startServer = async () => {
  try {
    await fastify.listen({ port: PORT, host: '0.0.0.0' });
    fastify.log.info(`[TS-Node] file-io server listening on ${PORT}`);
  } catch (err) {
    fastify.log.error(err);
    process.exit(1);
  }
};

startServer();
