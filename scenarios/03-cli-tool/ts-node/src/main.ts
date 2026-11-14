/**
 * 场景 03：命令行工具 — TS(Node) 实现（简化版 wc，commander 参数解析）
 *
 * Node CLI 工具特点：
 * 1. commander / yargs / cac 都是流行的参数解析库
 * 2. 开发快，但分发需要 Node.js 环境（或 pkg/nexe 打包）
 * 3. pkg/nexe 打包单文件大（~80MB+），因为内嵌了整个 Node.js runtime
 * 4. 启动速度 ~30-100ms（JIT 编译的 Node 比 Python 快）
 *
 * 和 Go/Rust 原生二进制对比：
 * - Node 生态最全但运行时最重
 * - 写 CLI 非常爽（npm 生态 + TS 类型安全）
 * - 分发是痛点（要 Node 或打包后体积大）
 */
import { Command } from 'commander';
import pino from 'pino';
import * as fs from 'fs';
import * as path from 'path';

// pino 初始化：JSON 格式 + stdout + 最低 DEBUG 级别
const logger = pino({
  level: process.env.LOG_LEVEL || 'debug',
  timestamp: pino.stdTimeFunctions.isoTime,
  transport: { target: 'pino/file', options: { destination: 1 } }
});

// 统计单个文件
function countFile(filePath: string): [number, number, number] {
  let content: string;
  try {
    content = fs.readFileSync(filePath, 'utf-8');
  } catch (err: any) {
    if (err.code === 'ENOENT') {
      logger.error({ msg: `count: cannot open '${filePath}': file not found` });
      process.exit(1);
    }
    logger.error({ msg: `count: read '${filePath}' failed: ${err.message}` });
    process.exit(1);
  }

  // 行数：与 wc -l 语义对齐（统计换行符个数；末尾换行不额外计一行）
  // 注意：content.split('\n').length 会把结尾换行后的空段也算进去，
  // 对以换行结尾的文件会多报 1 行，与 Go/Rust/Java/Python 实现不一致。
  const lines = content === ''
    ? 0
    : content.split('\n').length - (content.endsWith('\n') ? 1 : 0);

  // 词数：按空白分割，过滤空串
  const words = content.trim() === '' ? 0
    : content.trim().split(/\s+/).length;

  // 字符数（Unicode 感知：用 Array.from 处理 emoji 等）
  const chars = Array.from(content).length;

  return [lines, words, chars];
}

function printResult(
  label: string,
  lines: number,
  words: number,
  chars: number,
  options: { lines?: boolean; words?: boolean; chars?: boolean }
): void {
  // 注意：commander 把 `.option('-l, --lines')` 解析到 options.lines（长选项名），
  // 不是 options.l —— 写成 options.l 会永远 falsy，导致三个选项全部失效、无条件全量输出。
  const anyFlag = !!(options.lines || options.words || options.chars);
  const defaultAll = !anyFlag;

  const parts: string[] = [];
  if (options.lines || defaultAll) parts.push(`lines=${lines}`);
  if (options.words || defaultAll) parts.push(`words=${words}`);
  if (options.chars || defaultAll) parts.push(`chars=${chars}`);

  const out = parts.join(' ');
  if (label) {
    console.log(`${out}  ${label}`);
  } else {
    console.log(out);
  }
}

function main(): void {
  const program = new Command();

  program
    .name('count')
    .version('1.0.0')
    .description('简化版 wc — 统计文件行数、词数、字符数')
    .option('-l, --lines', '只统计行数 (lines)')
    .option('-w, --words', '只统计词数 (words)')
    .option('-c, --chars', '只统计字符数 (chars)')
    .argument('<files...>', '要统计的文件路径（支持多个）')
    .action((files: string[], options) => {
      const multi = files.length > 1;
      let totalL = 0, totalW = 0, totalC = 0;

      for (const f of files) {
        const [l, w, c] = countFile(f);
        if (multi) {
          printResult(f, l, w, c, options);
        }
        totalL += l;
        totalW += w;
        totalC += c;
      }

      if (multi) {
        logger.error({ msg: '---' });
      }

      const label = multi ? 'total' : '';
      printResult(label, totalL, totalW, totalC, options);
    });

  program.parse();
}

main();
