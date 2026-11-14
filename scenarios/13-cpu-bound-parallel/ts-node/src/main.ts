/**
 * 场景 13：CPU 密集并行计算 — TypeScript/Node 实现（fastify + worker_threads）
 *
 * 统一 API 契约：
 *   POST /compute
 *   {"task_count":8,"iterations":2000000,"concurrency":4}
 *   → {"total_tasks":8,"iterations":2000000,"concurrency":4,"cpu_cores":10,
 *      "total_time_ms":1234,"checksum":"<uint64 无符号十进制>",
 *      "results":[{"id":0,"checksum":"<uint64>","duration_ms":150}, ...]}
 *
 * 这个场景是 Node 最"难受"的一个，原因有两条：
 *
 * 1. **单线程**：Node 只有一个 JS 执行线程，CPU 密集任务会阻塞整个事件循环 ——
 *    连 /health 都响应不了。要并行就只能 `worker_threads`，
 *    而 worker 是**独立的 V8 隔离区**，不能共享 JS 对象，只能靠 postMessage 拷贝数据。
 *    （对比：Go/Rust 共享内存 + 线程/goroutine，Java 线程间也共享堆。）
 *
 * 2. **没有 64 位整数**：JS 的 number 是 IEEE-754 双精度浮点，只有 53 位整数精度。
 *    要与其他四门语言的 uint64 环绕语义**逐位对齐**，只能上 BigInt，
 *    而 BigInt 比 number 运算慢约一个数量级 —— 这是 Node 的"语言税"。
 *    工程上的规避手段是用 Math.imul 做 32 位双字模拟（快 5~10 倍），
 *    但实现复杂度陡增且极易写错，本场景刻意保留 BigInt 版本以展示这个真实取舍。
 *
 * 并发模型对照（同一需求，五门语言的"限流原语"）：
 *    Java   → Executors.newFixedThreadPool(concurrency)
 *    Go     → 带缓冲 channel 当信号量
 *    Rust   → AtomicUsize 计数器 + std::thread
 *    Python → ProcessPoolExecutor（GIL 所迫，必须换进程）
 *    TS     → 手动维护 Worker 池 + 任务队列（下面 40 行）
 */
import path from 'node:path';
import os from 'node:os';
import { Worker } from 'node:worker_threads';

import Fastify from 'fastify';
import pino from 'pino';

const PORT = 8139;

// pino 初始化：JSON 格式 + stdout + 最低 DEBUG 级别
const logger = pino({
  level: process.env.LOG_LEVEL || 'debug',
  timestamp: pino.stdTimeFunctions.isoTime,
  transport: { target: 'pino/file', options: { destination: 1 } }
});

/** BigInt 任意精度，不会自动溢出，必须手动截断才能与 uint64 对齐 */
const MASK = (1n << 64n) - 1n;

const DEFAULT_TASK_COUNT = 8;
const DEFAULT_ITERATIONS = 2_000_000;
const DEFAULT_CONCURRENCY = 4;

interface ComputeRequest {
  task_count?: number;
  iterations?: number;
  concurrency?: number;
}

interface TaskResult {
  id: number;
  checksum: string;
  duration_ms: number;
}

interface ComputeResponse {
  total_tasks: number;
  iterations: number;
  concurrency: number;
  cpu_cores: number;
  total_time_ms: number;
  checksum: string;
  results: TaskResult[];
}

const fastify = Fastify({ logger });

/**
 * 手动实现 Worker 池：创建 `concurrency` 个 worker，
 * 用「谁空下来就派下一个任务」的方式做负载均衡。
 *
 * 注意 worker 脚本是 worker.js（纯 JS），不是 .ts —— 原因见该文件头部注释。
 */
function runPool(taskCount: number, iterations: number, concurrency: number): Promise<TaskResult[]> {
  return new Promise<TaskResult[]>((resolve, reject) => {
    const results: TaskResult[] = new Array(taskCount);
    const workers: Worker[] = [];

    let nextId = 0;
    let finished = 0;
    let settled = false;

    const cleanup = (): void => {
      for (const w of workers) {
        void w.terminate();
      }
    };

    for (let w = 0; w < concurrency; w++) {
      const worker = new Worker(path.join(__dirname, 'worker.js'));
      workers.push(worker);

      // 派发下一个任务；没有剩余任务就静默等待（worker 会随 cleanup 一起结束）
      const dispatch = (): void => {
        if (nextId < taskCount) {
          const id = nextId++;
          worker.postMessage({ id, iterations });
        }
      };

      worker.on('message', (msg: TaskResult) => {
        results[msg.id] = msg;
        finished += 1;
        if (finished === taskCount) {
          if (!settled) {
            settled = true;
            cleanup();
            resolve(results);
          }
        } else {
          dispatch();
        }
      });

      worker.on('error', (err: Error) => {
        if (!settled) {
          settled = true;
          cleanup();
          reject(err);
        }
      });

      dispatch();
    }
  });
}

fastify.post('/compute', async (request, reply) => {
  const req = (request.body ?? {}) as ComputeRequest;

  // 缺省值填充 + 下界保护
  const taskCount = Math.max(1, Math.floor(Number(req.task_count) || DEFAULT_TASK_COUNT));
  const iterations = Math.max(1, Math.floor(Number(req.iterations) || DEFAULT_ITERATIONS));
  const concurrency = Math.min(
    Math.max(1, Math.floor(Number(req.concurrency) || DEFAULT_CONCURRENCY)),
    taskCount,
  );

  const startNs = process.hrtime.bigint();

  const results = await runPool(taskCount, iterations, concurrency);

  // 累加和取 uint64 环绕（加法模 2^64 满足交换律，与执行顺序无关）
  let sum = 0n;
  for (const r of results) {
    sum = (sum + BigInt(r.checksum)) & MASK;
  }

  const totalTimeMs = Number((process.hrtime.bigint() - startNs) / 1000000n);

  const resp: ComputeResponse = {
    total_tasks: taskCount,
    iterations,
    concurrency,
    cpu_cores: os.cpus().length,
    total_time_ms: totalTimeMs,
    checksum: sum.toString(),
    results,
  };

  reply.code(200);
  return resp;
});

fastify.get('/health', async () => ({
  service: 'cpu-bound-parallel-ts-node',
  cpu_cores: os.cpus().length,
}));

async function main(): Promise<void> {
  await fastify.listen({ port: PORT, host: '0.0.0.0' });
  logger.info({ msg: 'server starting', addr: `0.0.0.0:${PORT}` });
}

void main();
