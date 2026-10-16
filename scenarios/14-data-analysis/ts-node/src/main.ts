/**
 * 场景 14：数据分析处理 —— TS 用 danfojs-node（Node 世界的 DataFrame，已停更）。
 *
 * 数据集与其它语言逐位一致：amount = LCG(i+1) 高 32 位 % 100000，category = i % categories。
 * 注意：JS 没有原生 64 位整数，LCG 的 uint64 环绕必须用 BigInt（比 Number 慢一个数量级，
 * 这本身就是场景 13 已经展示过的"语言税"，在本场景的数据生成阶段再次出现）。
 *
 * 分位数统一 nearest-rank 口径（排序后取 ceil(p*n/100)-1 下标）：各库 quantile 默认
 * 插值方式不一，放任默认值必然跨语言对不齐，因此分位数与 Top-K 手写。
 */

import Fastify from "fastify";

// eslint-disable-next-line @typescript-eslint/no-var-requires
const dfd = require("danfojs-node");

const MULT = 6364136223846793005n;
const INC = 1442695040888963407n;
const MASK = (1n << 64n) - 1n;
const AMOUNT_MOD = 100_000n;
const PORT = 8144;

function amountOf(i: number): number {
  const h = ((BigInt(i) + 1n) * MULT + INC) & MASK; // BigInt 模拟 uint64 环绕
  return Number((h >> 32n) % AMOUNT_MOD);
}

interface GroupStat {
  category: string;
  count: number;
  sum: number;
  avg: number;
  p50: number;
  p95: number;
}

interface TopRow {
  id: number;
  category: string;
  amount: number;
}

interface AnalyzeResponse {
  rows: number;
  categories: number;
  groups: GroupStat[];
  top10: TopRow[];
  gen_ms: number;
  agg_ms: number;
  elapsed_ms: number;
}

/** nearest-rank 分位数：排序后取下标 ceil(p*n/100)-1。 */
function nearestRank(sorted: number[], p: number): number {
  const n = sorted.length;
  const idx = Math.max(0, Math.min(n - 1, Math.ceil((p * n) / 100) - 1));
  return sorted[idx];
}

function analyze(rows: number, cats: number): AnalyzeResponse {
  const t0 = Date.now();

  // ---- 数据生成（BigInt 保 uint64 语义；原始数组留给手写部分）----
  const ids: number[] = new Array(rows);
  const catIdx: number[] = new Array(rows);
  const amounts: number[] = new Array(rows);
  const catNames: string[] = new Array(rows);
  for (let i = 0; i < rows; i++) {
    ids[i] = i;
    catIdx[i] = i % cats;
    amounts[i] = amountOf(i);
    catNames[i] = "cat-" + catIdx[i];
  }

  const df = new dfd.DataFrame({ id: ids, category: catNames, amount: amounts });
  const t1 = Date.now();

  // ---- 分组聚合：danfojs 一行 groupby（生态库 vs 手写循环的对比位）----
  const sumDf = df.groupby(["category"]).col(["amount"]).sum();
  const cntDf = df.groupby(["category"]).col(["amount"]).count();
  const sumMap = new Map<string, number>();
  const cntMap = new Map<string, number>();
  for (const row of sumDf.values as [string, number][]) {
    sumMap.set(String(row[0]), Number(row[1]));
  }
  for (const row of cntDf.values as [string, number][]) {
    cntMap.set(String(row[0]), Number(row[1]));
  }

  // ---- 分位数 / Top-K：统一口径手写 ----
  const buckets: number[][] = Array.from({ length: cats }, () => [] as number[]);
  for (let i = 0; i < rows; i++) {
    buckets[catIdx[i]].push(amounts[i]);
  }
  const groups: GroupStat[] = [];
  for (let c = 0; c < cats; c++) {
    const vals = buckets[c];
    if (vals.length === 0) continue;
    vals.sort((a, b) => a - b);
    const sum = sumMap.get("cat-" + c) ?? 0;
    const cnt = cntMap.get("cat-" + c) ?? vals.length;
    groups.push({
      category: "cat-" + c,
      count: cnt,
      sum,
      avg: sum / cnt,
      p50: nearestRank(vals, 50),
      p95: nearestRank(vals, 95),
    });
  }
  groups.sort((a, b) => (a.category < b.category ? -1 : a.category > b.category ? 1 : 0));

  // Top-10：amount 降序，id 升序
  const order: number[] = Array.from({ length: rows }, (_, i) => i);
  order.sort((a, b) =>
    amounts[a] !== amounts[b] ? amounts[b] - amounts[a] : ids[a] - ids[b]
  );
  const top10: TopRow[] = order.slice(0, 10).map((i) => ({
    id: ids[i],
    category: "cat-" + catIdx[i],
    amount: amounts[i],
  }));

  const t2 = Date.now();
  return {
    rows,
    categories: cats,
    groups,
    top10,
    gen_ms: t1 - t0,
    agg_ms: t2 - t1,
    elapsed_ms: t2 - t0,
  };
}

async function main() {
  const app = Fastify({ logger: false });

  app.get<{ Reply: Record<string, string> }>("/health", async () => ({
    service: "data-analysis",
    lang: "ts-node",
    engine: "danfojs-node",
  }));

  app.post<{ Body: { rows?: number; categories?: number } }>(
    "/analyze",
    async (req, reply) => {
      const rows = req.body?.rows ?? 200_000;
      const cats = req.body?.categories ?? 8;
      if (rows < 1000 || rows > 2_000_000) {
        return reply.code(400).send({ error: "rows must be in [1000, 2000000]" });
      }
      if (cats < 1 || cats > 64) {
        return reply.code(400).send({ error: "categories must be in [1, 64]" });
      }
      return reply.send(analyze(rows, cats));
    }
  );

  await app.listen({ port: PORT, host: "0.0.0.0" });
  console.log(`data-analysis (ts-node/danfojs) listening on :${PORT}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
