/**
 * 场景 02：并发任务处理 — TypeScript Node 实现 (fastify + Promise)
 *
 * Node.js 并发模型特点：
 * 1. **单线程事件循环** — 和 Python asyncio 本质相同
 * 2. IO 密集型任务极高效，因为 async 操作不会阻塞主循环
 * 3. 但 CPU 密集型任务会阻塞整个事件循环
 * 4. libuv 线程池处理系统级 IO（文件、DNS、加密）
 *
 * 和其他语言的本质区别：
 * - Java/Go/Rust：多线程真并行
 * - Python asyncio / TS 事件循环：单线程伪并行（靠 IO 不阻塞来提高效率）
 *
 * 并发限流原语：手写一个简单的 p-limit（不引入额外依赖）
 * 思路：用一个队列存 Promise 工厂函数，同时最多 N 个在执行
 */
import Fastify, { FastifyReply } from 'fastify';

const PORT = 8089;

// ========== 手写 p-limit ==========
/**
 * 简单的并发限流实现（类似 p-limit 库，但零依赖）
 * 思路：维护一个待执行队列 + 正在执行的计数
 * 当正在执行的数量 < limit 时，从队列取出执行
 */
function pLimit<T>(limit: number) {
  let active = 0;
  // 队列里存的是 run 闭包（() => void），不是任务工厂本身 ——
  // 曾经这里声明成 Array<() => Promise<T>>，tsc 直接报 TS2345（tsx 不类型检查所以长期潜伏）
  const queue: Array<() => void> = [];

  function enqueue(fn: () => Promise<T>): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      const run = () => {
        active++;
        Promise.resolve()
          .then(fn)
          .then(resolve, reject)
          .then(() => {
            active--;
            if (queue.length > 0) {
              // 队列里还有待执行的，取一个出来
              const next = queue.shift()!;
              runTask(next);
            }
          });
      };

      if (active < limit) {
        run();
      } else {
        queue.push(run);
      }
    });
  }

  // 触发执行队列里的任务（递归入口）
  function runTask(task: () => void) {
    // 这个函数会在 enqueue 的 active-- 之后被调用
    // 但因为我们在 enqueue 里已经处理了，这里是空的
    task();
  }

  return enqueue;
}
// ================================

interface RunRequest {
  task_count: number;
  task_delay_ms: number;
  concurrency: number;
}

interface TaskResult {
  id: number;
  status: string;
  duration_ms: number;
}

interface RunResponse {
  total_tasks: number;
  concurrency: number;
  total_time_ms: number;
  throughput: number;
  task_delay_ms: number;
  results: TaskResult[];
}

const fastify = Fastify({ logger: true });

// 单个异步任务：sleep 指定毫秒后返回
function executeTask(id: number, delayMs: number): Promise<TaskResult> {
  const start = performance.now();
  return new Promise((resolve) => {
    setTimeout(() => {
      const durationMs = Math.round(performance.now() - start);
      resolve({ id, status: 'ok', duration_ms: durationMs });
    }, delayMs);
  });
}

// 统一契约（与其余四门对齐）：
//   - 字段缺省 → 默认值 100/100/10
//   - 显式非法值 / 非整数 / 空 body → 400
//   - 方法不是 POST → 405（fastify 默认对未匹配方法返回 404，这里显式抹平）
function badRequest(reply: FastifyReply, message: string) {
  reply.code(400);
  return { error: message };
}

fastify.all('/run', async (request, reply) => {
  if (request.method !== 'POST') {
    reply.code(405);
    return { error: 'method not allowed' };
  }

  const body = request.body;
  if (body === undefined || body === null || typeof body !== 'object' || Array.isArray(body)) {
    return badRequest(reply, 'request body must be a JSON object');
  }
  const req = body as Partial<RunRequest>;

  // 缺省 → 默认值
  const taskCount = req.task_count ?? 100;
  const delayMs = req.task_delay_ms ?? 100;
  const concurrencyRaw = req.concurrency ?? 10;

  // 显式非法值 → 400（不做静默夹取）
  if (!Number.isInteger(taskCount) || taskCount < 1) {
    return badRequest(reply, 'task_count must be an integer >= 1');
  }
  if (!Number.isInteger(delayMs) || delayMs < 0) {
    return badRequest(reply, 'task_delay_ms must be an integer >= 0');
  }
  if (!Number.isInteger(concurrencyRaw) || concurrencyRaw < 1) {
    return badRequest(reply, 'concurrency must be an integer >= 1');
  }

  // 并发数不超过任务数（契约行为）
  const concurrency = Math.min(concurrencyRaw, taskCount);

  const start = performance.now();

  // ========== TS(Node) 并发核心 ==========
  const limit = pLimit<TaskResult>(concurrency);

  // 创建 taskCount 个 Promise，通过 limit 控制同时执行数
  const promises: Promise<TaskResult>[] = [];
  for (let i = 0; i < taskCount; i++) {
    const taskId = i;
    promises.push(limit(() => executeTask(taskId, delayMs)));
  }

  // Promise.all 等待全部完成（保持顺序）
  const results = await Promise.all(promises);
  // ======================================

  const totalMs = Math.round(performance.now() - start);
  const throughput = totalMs > 0 ? Math.round((taskCount * 1000 / totalMs) * 100) / 100 : taskCount;

  const response: RunResponse = {
    total_tasks: taskCount,
    concurrency,
    total_time_ms: totalMs,
    throughput,
    task_delay_ms: delayMs,
    results,
  };

  return response;
});

const startServer = async () => {
  try {
    await fastify.listen({ port: PORT, host: '0.0.0.0' });
    fastify.log.info(`[TS-Node] concurrent-task server listening on ${PORT}`);
  } catch (err) {
    fastify.log.error(err);
    process.exit(1);
  }
};

startServer();
