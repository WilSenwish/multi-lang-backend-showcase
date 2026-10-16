/**
 * 场景 16：大文件流式处理 —— TS(Node) 用固定缓冲 + 手写行边界处理。
 *
 * 语义契约（五门语言必须逐字一致，见场景 README）：
 *   1. 生成一个确定性的定长行文件（每行 10 字节：NNN,AAAAA\n），生成过程本身也是流式的
 *   2. 以 chunk_kib × 1024 字节的固定缓冲读取，**绝不整体读入内存**
 *   3. 行可能跨越 chunk 边界 → 用"残余行拼接"处理，不能假设 chunk 边界 = 行边界
 *   4. 逐行解析 amount，过滤 amount >= min_amount，输出 NNN,BBBBBB\n（11 字节），流式写
 *   5. 输入/输出各算一份 SHA-256（取前 8 字节 hex），处理完删除两个临时文件
 *
 * Node 的取舍：
 *   - Buffer 是堆外内存：`process.memoryUsage().heapUsed` **看不见**它。
 *     所以"Node 的堆没涨"根本不能证明"内存没涨" —— 必须用 RSS 口径，
 *     而且 RSS 没有峰值 API，只能在循环里轮询采样取最大值
 *   - 没有 64 位整数：序列生成只能用 BigInt（比 Number 慢一个量级，见 README 实测）
 *   - 这里刻意不用 fs.createReadStream：它的内部 highWaterMark 缓冲是隐藏的，
 *     本场景要的是"缓冲大小由我控制"，所以直接 readSync/writeSync + 显式 position
 */

import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import Fastify from "fastify";

const PORT = 8154;
/** 确定性数据序列：h(i) = (i+1)*MULT + INC（mod 2^64），amount = (h >> 32) % 100000 */
const MULT = 6364136223846793005n;
const INC = 1442695040888963407n;
const MASK = (1n << 64n) - 1n;
const LINE_IN = 10; // "%03d,%05d\n"
const LINE_OUT = 11; // "%03d,%06d\n"
const GEN_BUF = 64 * 1024;

interface StreamRequest {
  size_mb?: number;
  chunk_kib?: number;
  min_amount?: number;
}

/** RSS / 堆采样：Node 没有 ru_maxrss（峰值）接口，只能轮询当前值取最大 */
let rssPeak = 0;
let heapPeak = 0;
function sampleMemory(): void {
  const m = process.memoryUsage();
  if (m.rss > rssPeak) rssPeak = m.rss;
  if (m.heapUsed > heapPeak) heapPeak = m.heapUsed;
}

function writeAll(fd: number, buf: Buffer, len: number): void {
  let off = 0;
  while (off < len) {
    off += fs.writeSync(fd, buf, off, len - off);
  }
}

/** 手写定宽数字（避免 toString/padStart 每行的字符串分配） */
function writeFixed(buf: Buffer, pos: number, v: number, width: number): number {
  for (let k = width - 1; k >= 0; k--) {
    buf[pos + k] = 48 + (v % 10);
    v = Math.floor(v / 10);
  }
  return pos + width;
}

// ---- 阶段一：流式生成源文件 ------------------------------------------------
function generate(file: string, lines: number): void {
  const fd = fs.openSync(file, "w");
  const buf = Buffer.allocUnsafe(GEN_BUF);
  let len = 0;
  let h = INC;
  for (let i = 0; i < lines; i++) {
    h = (h + MULT) & MASK;
    const amount = Number((h >> 32n) % 100000n);
    const g = i % 1000;
    if (len + LINE_IN > GEN_BUF) {
      writeAll(fd, buf, len);
      len = 0;
    }
    buf[len++] = 48 + Math.floor(g / 100);
    buf[len++] = 48 + Math.floor((g / 10) % 10);
    buf[len++] = 48 + (g % 10);
    buf[len++] = 44; // ','
    len = writeFixed(buf, len, amount, 5);
    buf[len++] = 10; // '\n'
  }
  if (len > 0) writeAll(fd, buf, len);
  fs.closeSync(fd);
}

// ---- 阶段二：流式处理（读 → 解析 → 过滤 → 转换 → 写） ---------------------
function process_(
  src: string,
  dst: string,
  chunk: number,
  minAmount: number,
): Record<string, number | string> {
  const hIn = crypto.createHash("sha256");
  const hOut = crypto.createHash("sha256");
  const fdIn = fs.openSync(src, "r");
  const fdOut = fs.openSync(dst, "w");

  const buf = Buffer.allocUnsafe(chunk);
  // pending 保存"上一个 chunk 剩下的半行"，容量固定 → 内存与文件大小无关
  const pending = Buffer.allocUnsafe(chunk + LINE_IN);
  let pendingLen = 0;
  const outBuf = Buffer.allocUnsafe(chunk + LINE_OUT);
  let outLen = 0;

  let pos = 0;
  let chunks = 0;
  let bytesRead = 0;
  let linesRead = 0;
  let bytesWritten = 0;
  let linesWritten = 0;
  const t0 = Date.now();

  for (;;) {
    let filled = 0;
    while (filled < chunk) {
      const n = fs.readSync(fdIn, buf, filled, chunk - filled, pos);
      if (n === 0) break; // EOF
      filled += n;
      pos += n;
    }
    if (filled === 0) break;

    chunks++;
    bytesRead += filled;
    hIn.update(buf.subarray(0, filled));
    if (chunks % 256 === 0) sampleMemory();

    buf.copy(pending, pendingLen, 0, filled);
    pendingLen += filled;

    let start = 0;
    for (;;) {
      // 不能用 pending.indexOf(10, start)：pending 尾部是未初始化的旧字节，会误命中
      let nl = -1;
      for (let k = start; k < pendingLen; k++) {
        if (pending[k] === 10) {
          nl = k;
          break;
        }
      }
      if (nl === -1) break;

      linesRead++;
      if (nl - start >= LINE_IN - 1) {
        let amount = 0;
        for (let k = start + 4; k < start + 9; k++) {
          amount = amount * 10 + (pending[k] - 48);
        }
        if (amount >= minAmount) {
          pending.copy(outBuf, outLen, start, start + 4); // "NNN," 原样拷贝
          outLen += 4; // ⚠️ copy() 不会推进写指针，漏了这行后面的数字会把前缀覆盖掉
          outLen = writeFixed(outBuf, outLen, amount * 2, 6);
          outBuf[outLen++] = 10;
          linesWritten++;
          bytesWritten += LINE_OUT;
          if (outLen + LINE_OUT > outBuf.length) {
            hOut.update(outBuf.subarray(0, outLen));
            writeAll(fdOut, outBuf, outLen);
            outLen = 0;
          }
        }
      }
      start = nl + 1;
    }
    if (start > 0) {
      pending.copy(pending, 0, start, pendingLen);
      pendingLen -= start;
    }
    if (filled < chunk) break; // 没读满 = EOF
  }
  if (outLen > 0) {
    hOut.update(outBuf.subarray(0, outLen));
    writeAll(fdOut, outBuf, outLen);
  }
  fs.closeSync(fdIn);
  fs.closeSync(fdOut);

  const ms = Date.now() - t0;
  return {
    bytes_read: bytesRead,
    lines_read: linesRead,
    bytes_written: bytesWritten,
    lines_written: linesWritten,
    checksum: hIn.digest("hex").slice(0, 16),
    output_checksum: hOut.digest("hex").slice(0, 16),
    chunks,
    proc_ms: ms,
    throughput_mb_s: ms > 0 ? bytesRead / (1024 * 1024) / (ms / 1000) : 0,
  };
}

function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
}

const app = Fastify({ logger: false });

app.post("/stream/process", async (request, reply) => {
  const req = (request.body ?? {}) as StreamRequest;
  const sizeMb = clamp(req.size_mb ?? 32, 1, 512);
  const chunkKib = clamp(req.chunk_kib ?? 64, 1, 4096);
  const minAmount = clamp(req.min_amount ?? 50000, 0, 99999);

  const lines = Math.floor((sizeMb * 1024 * 1024) / LINE_IN);
  const tag = `stream16-${process.pid}-${Date.now()}`;
  const src = path.join(os.tmpdir(), `${tag}.in`);
  const dst = path.join(os.tmpdir(), `${tag}.out`);

  rssPeak = 0;
  heapPeak = 0;
  sampleMemory();
  const rssBefore = rssPeak;
  const tAll = Date.now();

  generate(src, lines);
  const genMs = Date.now() - tAll;

  const res = process_(src, dst, chunkKib * 1024, minAmount);
  sampleMemory();

  // 真实写出的字节数（stat 文件，而不是信任计数器）—— 计数器可能与真实写入脱节
  const outputFileBytes = fs.statSync(dst).size;

  // 清理临时文件：不删的话多跑几次就把磁盘撑满了
  const existed = fs.existsSync(src);
  for (const p of [src, dst]) {
    try {
      fs.unlinkSync(p);
    } catch {
      /* ignore */
    }
  }
  const cleanup = existed && !fs.existsSync(src) && !fs.existsSync(dst);

  return reply.send({
    lang: "ts-node",
    size_mb: sizeMb,
    chunk_kib: chunkKib,
    min_amount: minAmount,
    ...res,
    gen_ms: genMs,
    elapsed_ms: Date.now() - tAll,
    output_file_bytes: outputFileBytes,
    rss_before_bytes: rssBefore,
    rss_peak_bytes: rssPeak,
    rss_delta_bytes: rssPeak - rssBefore,
    peak_heap_bytes: heapPeak,
    heap_metric: "node.process.memoryUsage().heapUsed（不含 Buffer 堆外内存，故只看它会误判）",
    cleanup,
  });
});

app.listen({ port: PORT, host: "0.0.0.0" }, (err) => {
  if (err) {
    console.error(err);
    process.exit(1);
  }
  console.log(`large-file-streaming (ts-node) listening on ${PORT}`);
});
