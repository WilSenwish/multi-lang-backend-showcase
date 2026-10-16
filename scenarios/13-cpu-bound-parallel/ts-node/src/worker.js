'use strict';
/**
 * 场景 13：CPU 密集并行计算 — Node worker 线程脚本
 *
 * 为什么这个文件写成纯 JS 而不是 TS：
 *   worker_threads 直接按文件路径加载脚本，不会经过 tsx 的 TypeScript loader。
 *   写成 .ts 会让 `tsx src/main.ts`（dev）下的 worker 加载失败。
 *   改成 .js + tsconfig 的 allowJs=true，tsc 会把它一并复制到 dist/，
 *   于是 dev（tsx）与 prod（node dist/main.js）两种启动方式都能正常工作。
 *
 * 为什么必须用 worker_threads：
 *   Node 是单线程事件循环，任何 JS 计算都会阻塞整个进程 ——
 *   在主线程里跑 CPU 密集任务，服务会连健康检查都响应不了。
 *   worker_threads 是 Node 里唯一能真正并行执行 JS 的官方手段（每个 worker 独立 V8 隔离区）。
 *
 * 为什么必须用 BigInt：
 *   JS 的 number 是 IEEE-754 双精度浮点，只有 53 位有效整数精度，
 *   无法表示 uint64（需要 64 位）。要与其他语言的 uint64 环绕语义逐位对齐，
 *   唯一正确做法是 BigInt。代价是 BigInt 运算比 number 慢一个数量级 ——
 *   这就是 Node 在"需要精确 64 位整数"场景下的**语言税**。
 */

const { parentPort } = require('node:worker_threads');

// MMIX 线性同余发生器常数：state = state * MULT + INC (mod 2^64)
const MULT = 6364136223846793005n;
const INC = 1442695040888963407n;
// BigInt 是任意精度，不会自动溢出，必须手动截断到 64 位才能与 uint64 语义一致
const MASK = (1n << 64n) - 1n;

parentPort.on('message', (msg) => {
  const { id, iterations } = msg;

  const t0 = process.hrtime.bigint();

  let state = BigInt(id + 1);
  // 循环计数器保持 Number：iterations <= 2^53，且 Number 自增比 BigInt 快得多
  for (let i = 0; i < iterations; i++) {
    state = (state * MULT + INC) & MASK;
  }
  // state 大而 checksum 必须在 2^64 内，所以先取模再转字符串
  const checksum = (state & MASK).toString();

  const durationMs = Number((process.hrtime.bigint() - t0) / 1000000n);

  parentPort.postMessage({ id, checksum, durationMs });
});
