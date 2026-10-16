/**
 * 场景 15：结构化并发 + 取消传播 —— TS(Node) 用 AbortController / AbortSignal。
 *
 * 语义契约（五门语言必须逐字一致，见场景 README）：
 *   - 扇出 tasks 个子任务，id = 0..tasks-1，全部并发启动
 *   - id == fail_index 的子任务在 fail_after_ms 后"失败"；其余子任务跑满 task_ms 后"完成"
 *   - 任一子任务失败 / 父作用域超时 → 取消信号必须传播到所有兄弟任务（cancelled）
 *   - 作用域退出时所有子任务必须已结束（结构化保证），leaked 恒为 0
 *
 * Node 的取舍：AbortSignal 是**标准库的取消传播协议**（fetch / fs / 定时器都能消费），
 * 传播机制一等公民；但"结构化"要自己写 —— 没有 TaskGroup，
 * fail-fast 需要手写"首个失败 → controller.abort()"，并用 Promise.all 收尾。
 */

import Fastify from "fastify";

const PORT = 8149;

type Outcome = "pending" | "completed" | "cancelled" | "failed";

/** 运行时统计（供 /stats 暴露，验证器用它做"取消是否真的生效"的延迟判定） */
const STATS = { active: 0, started: 0, completed: 0, cancelled: 0, failed: 0 };

interface FanoutRequest {
  tasks?: number;
  task_ms?: number;
  fail_index?: number;
  fail_after_ms?: number;
  timeout_ms?: number;
}

/**
 * 可中断的等待：等满 ms 返回 true；signal 被 abort 则立刻返回 false。
 * Node 侧取消传播的全部实现就在这里 —— signal 是标准协议，谁都能消费。
 */
function sleepCancel(ms: number, signal: AbortSignal): Promise<boolean> {
  return new Promise<boolean>((resolve) => {
    if (signal.aborted) {
      resolve(false);
      return;
    }
    function cleanup() {
      signal.removeEventListener("abort", onAbort);
    }
    function onAbort() {
      clearTimeout(timer);
      cleanup();
      resolve(false);
    }
    const timer = setTimeout(() => {
      cleanup();
      resolve(true);
    }, ms);
    signal.addEventListener("abort", onAbort, { once: true });
  });
}

function validate(tasks: number, taskMs: number, failIndex: number, failAfterMs: number, timeoutMs: number): string | null {
  if (!(tasks >= 1 && tasks <= 64)) return "tasks must be in [1, 64]";
  if (!(taskMs >= 1 && taskMs <= 10000)) return "task_ms must be in [1, 10000]";
  if (!(failIndex >= -1 && failIndex < tasks)) return "fail_index must be in [-1, tasks)";
  if (!(failAfterMs >= 0 && failAfterMs <= 10000)) return "fail_after_ms must be in [0, 10000]";
  if (!(timeoutMs >= 0 && timeoutMs <= 10000)) return "timeout_ms must be in [0, 10000]";
  return null;
}

const app = Fastify({ logger: false });

app.get("/health", async () => ({
  service: "structured-concurrency",
  lang: "ts-node",
  engine: "AbortController + Promise.all",
}));

app.get("/stats", async () => ({
  lang: "ts-node",
  active_tasks: STATS.active,
  started: STATS.started,
  completed: STATS.completed,
  cancelled: STATS.cancelled,
  failed: STATS.failed,
}));

app.post("/fanout", async (req, reply) => {
  const body = (req.body ?? {}) as FanoutRequest;
  const tasks = body.tasks ?? 6;
  const taskMs = body.task_ms ?? 300;
  const failIndex = body.fail_index ?? -1;
  const failAfterMs = body.fail_after_ms ?? 100;
  const timeoutMs = body.timeout_ms ?? 0;

  const err = validate(tasks, taskMs, failIndex, failAfterMs, timeoutMs);
  if (err) {
    return reply.code(400).send({ error: err });
  }

  const t0 = Date.now();
  const controller = new AbortController();
  const { signal } = controller;

  // 父作用域 deadline：到点就 abort，取消沿 signal 传播到所有子任务
  let timer: NodeJS.Timeout | undefined;
  if (timeoutMs > 0) {
    timer = setTimeout(() => controller.abort(new Error("scope timeout")), timeoutMs);
  }

  const outcomes: Outcome[] = new Array<Outcome>(tasks).fill("pending");

  // 结构化收尾：Promise.all 等到所有子任务都落定（abort 会让它们提前 resolve 为 cancelled）
  await Promise.all(
    Array.from({ length: tasks }, (_, i) =>
      (async () => {
        STATS.started += 1;
        STATS.active += 1;
        try {
          if (i === failIndex) {
            const finished = await sleepCancel(failAfterMs, signal);
            if (finished) {
              outcomes[i] = "failed";
              STATS.failed += 1;
              // fail-fast：首个失败立刻 abort，取消传播给兄弟任务
              controller.abort(new Error(`task ${i} failed`));
            } else {
              outcomes[i] = "cancelled";
              STATS.cancelled += 1;
            }
            return;
          }
          const finished = await sleepCancel(taskMs, signal);
          if (finished) {
            outcomes[i] = "completed";
            STATS.completed += 1;
          } else {
            outcomes[i] = "cancelled";
            STATS.cancelled += 1;
          }
        } finally {
          STATS.active -= 1;
        }
      })()
    )
  );

  if (timer) clearTimeout(timer);
  const elapsedMs = Date.now() - t0;

  const completed: number[] = [];
  const cancelled: number[] = [];
  let failed = -1;
  for (let i = 0; i < tasks; i++) {
    if (outcomes[i] === "completed") completed.push(i);
    else if (outcomes[i] === "failed") failed = i;
    else cancelled.push(i); // pending 兜底：视为被取消，保证契约字段完整
  }

  const outcome = failed >= 0 ? "failed" : cancelled.length > 0 ? "timeout" : "completed";

  return {
    lang: "ts-node",
    tasks,
    task_ms: taskMs,
    fail_index: failIndex,
    fail_after_ms: failAfterMs,
    timeout_ms: timeoutMs,
    outcome,
    completed,
    cancelled,
    failed,
    elapsed_ms: elapsedMs,
    leaked: STATS.active,
  };
});

app.listen({ port: PORT, host: "0.0.0.0" }).then(() => {
  console.log(`structured-concurrency (ts-node/AbortController) listening on ${PORT}`);
});
