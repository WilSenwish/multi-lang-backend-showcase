/**
 * 场景 17：错误处理深水区 —— TS(Node) 版本。
 *
 * 语义契约（五门语言必须逐字一致，见场景 README）：
 *   GET /errors/{kind} —— 五种"错误形态"，每一种都必须落成同一个结构化响应体：
 *     - not_found      → 404 NOT_FOUND          cause_chain = ["user 42 not found"]
 *     - validation     → 400 VALIDATION_FAILED  details = ["email: required", "age: must be >= 0"]
 *     - wrap_chain     → 500 WRAPPED            cause_chain 四层，最外层 → 根因
 *     - panic          → 500 INTERNAL           未捕获异常被兜底，recovered=true，进程必须存活
 *     - async_detached → 202 ACCEPTED           错误发生在脱离请求上下文的 Promise 里
 *   GET /stats → handled / unhandled / panics_recovered / last_unhandled / last_trace_id
 *   请求头 X-Trace-Id 必须原样回显。
 *
 * TS(Node) 的取舍：
 *   - `throw` 可以扔**任何值**（`throw "oops"` 完全合法）—— 类型系统不知道函数会抛什么，
 *     `catch (e)` 里的 `e` 默认是 `unknown`，必须自己窄化，`e.message` 这一行就是事故源头。
 *   - `Error.cause` 是 ES2022 才进标准的：tsconfig 的 target/lib 低于 ES2022 时
 *     `new Error(msg, { cause })` 会静默丢掉 cause（编译能过，链是断的）。
 *     而且 `console.log(err)` 默认**不打印 cause** —— 排查时极易误判"没有根因"。
 *   - ⭐ 深水区：Node ≥ 15 默认 `--unhandled-rejections=throw`，一个没人 await 的 rejected
 *     promise **会直接终止进程**。这是五门语言里唯一"默认失败得很大声"的一个 ——
 *     但也就意味着：不装 `unhandledRejection` 钩子，服务会整个挂掉，而不只是丢一条错误。
 */

import Fastify from "fastify";
import pino from "pino";

const PORT = 8159;

// pino 初始化：JSON 格式 + stdout + 最低 DEBUG 级别
const logger = pino({
  level: process.env.LOG_LEVEL || 'debug',
  timestamp: pino.stdTimeFunctions.isoTime,
  transport: { target: 'pino/file', options: { destination: 1 } }
});

interface ErrorBody {
  kind: string;
  code: string;
  message: string;
  trace_id: string;
  cause_chain: string[];
  details: string[];
  stack_present: boolean;
  recovered: boolean;
}

interface StatsBody {
  handled: number;
  unhandled: number;
  panics_recovered: number;
  last_unhandled: string;
  last_trace_id: string;
}

const state = {
  handled: 0,
  unhandled: 0,
  panics: 0,
  lastUnhandled: "",
  lastTraceId: "",
  seq: 0,
};

class AppError extends Error {
  constructor(
    public code: string,
    message: string,
    public httpStatus: number,
    public details: string[] = [],
    cause?: unknown,
  ) {
    // ⭐ cause 必须显式传第二个参数；tsconfig 的 target 低于 ES2022 时这行会静默失效
    super(message, cause !== undefined ? { cause } : undefined);
    this.name = "AppError";
  }
}

function body(
  kind: string,
  code: string,
  message: string,
  traceId: string,
  chain: string[],
  details: string[],
  stack: boolean,
  recovered: boolean,
): ErrorBody {
  return {
    kind,
    code,
    message,
    trace_id: traceId,
    cause_chain: chain,
    details,
    stack_present: stack,
    recovered,
  };
}

/** 沿 Error.cause 收集消息：最外层 → 根因。cause 可能是任意值，必须逐层窄化。 */
function causeChain(err: unknown): string[] {
  const out: string[] = [];
  let cur: unknown = err;
  while (cur !== undefined && cur !== null && out.length < 32) {
    out.push(cur instanceof Error ? cur.message : String(cur));
    cur = cur instanceof Error ? cur.cause : undefined;
  }
  return out;
}

function kindOf(url: string): string {
  const marker = "/errors/";
  const i = url.indexOf(marker);
  return i >= 0 ? decodeURIComponent(url.slice(i + marker.length).split("?")[0]) : "";
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function detachedWork(): Promise<void> {
  await sleep(120);
  throw new Error("async-boom-17");
}

// ⭐ 深水区：不装这个钩子，Node ≥ 15 会直接终止进程（默认 --unhandled-rejections=throw）。
// 装了之后它既是"观测点"，也是"免死金牌" —— 二者是同一个机制。
process.on("unhandledRejection", (reason: unknown) => {
  state.unhandled += 1;
  state.lastUnhandled = reason instanceof Error ? reason.message : String(reason);
});

const app = Fastify({ logger });

app.setErrorHandler((err: unknown, req, reply) => {
  state.handled += 1;
  const traceId =
    (req.headers["x-trace-id"] as string | undefined) ?? `tid-${++state.seq}`;

  if (err instanceof AppError) {
    return reply.status(err.httpStatus).send(
      body(kindOf(req.url), err.code, err.message, traceId, causeChain(err), err.details, false, false),
    );
  }

  state.panics += 1;
  const message = err instanceof Error ? err.message : String(err);
  const stack = err instanceof Error && typeof err.stack === "string" && err.stack.length > 0;
  return reply
    .status(500)
    .send(body("panic", "INTERNAL", message, traceId, causeChain(err), [], stack, true));
});

app.get<{ Params: { kind: string } }>("/errors/:kind", async (req, reply) => {
  const kind = req.params.kind;
  const headerTid = req.headers["x-trace-id"] as string | undefined;
  const traceId = headerTid ?? `tid-${++state.seq}`;
  state.lastTraceId = traceId;

  switch (kind) {
    case "not_found":
      throw new AppError("NOT_FOUND", "user 42 not found", 404);

    case "validation":
      throw new AppError("VALIDATION_FAILED", "invalid request", 400, [
        "email: required",
        "age: must be >= 0",
      ]);

    case "wrap_chain": {
      const root = new Error("db: row 42 not found");
      const repo = new AppError("REPO", "repository: load user", 500, [], root);
      const svc = new AppError("SERVICE", "service: get profile", 500, [], repo);
      throw new AppError("WRAPPED", "handler: GET /errors/wrap_chain", 500, [], svc);
    }

    case "panic":
      // 未捕获异常：交给 setErrorHandler 兜底
      throw new Error("boom-17");

    case "async_detached":
      // 没人 await 这个 promise：它 reject 时会走 unhandledRejection
      void detachedWork();
      return reply
        .status(202)
        .send(body("async_detached", "ACCEPTED", "async work spawned", traceId, [], [], false, false));

    default: {
      const msg = `unknown kind: ${kind}`;
      return reply.status(404).send(body(kind, "UNKNOWN_KIND", msg, traceId, [msg], [], false, false));
    }
  }
});

app.get("/stats", async (): Promise<StatsBody> => ({
  handled: state.handled,
  unhandled: state.unhandled,
  panics_recovered: state.panics,
  last_unhandled: state.lastUnhandled,
  last_trace_id: state.lastTraceId,
}));

app
  .listen({ port: PORT, host: "127.0.0.1" })
  .then(() => {
    logger.info({ msg: 'server starting', addr: `127.0.0.1:${PORT}` });
  })
  .catch((err) => {
    logger.error({ err }, 'server failed to start');
    process.exit(1);
  });
