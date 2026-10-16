# 场景 14：数据分析处理（DataFrame 聚合）

## 业务描述

统一实现一份**确定性数据集**的分组聚合分析：

1. 生成 `rows` 行销售记录（默认 20 万行，可到 200 万）：
   - `amount(i) = (LCG(i+1) >> 32) % 100000`（0 ~ 99999 的整数）
   - `category(i) = i % categories`（默认 8 组：cat-0 ~ cat-7）
2. 按分组聚合：**count / sum / avg / p50 / p95**
3. 全量 **Top-10**（amount 降序，平局按 id 升序）
4. 返回耗时拆解（生成 / 聚合）

> 数据集是**行号的纯函数**——不依赖随机数种子、不需要造数据文件，五种语言生成逐位一致的数据，
> 因此聚合结果可以做**跨语言契约级比对**（这是本场景验证的核心，见下文「验证方式」）。

## 技术选型

| 语言 | 分析层 | 定位 |
|------|--------|------|
| Python | **pandas 2.x/3.x** | 生态王者：`df.groupby("category")` 一行流；p50/p95 一行 `quantile`（但口径要统一，见下） |
| Rust | **polars 0.55** | 性能王者：lazy `group_by().agg()`，比 pandas 快数倍，是"既有生态又有性能"的代表 |
| Java | **tablesaw 0.44** | Java 世界的 DataFrame：`table.summarize("amount", count, sum).by("category")` 能用，但 API 明显更啰嗦，生态弱势方 |
| Go | **gonum v0.17（stat 包）** | **没有 DataFrame**：分组要手写 map 分桶，gonum 只提供 `stat.Mean` 这类统计函数 |
| TS(Node) | **danfojs-node 1.2** | 已停更的 DataFrame 库（2022 年后无更新）；实测在 Node 24 可跑（见「选型思考」的坑） |

### 特别关注：分位数口径必须统一

各库 quantile **默认插值方式不同**（pandas 默认 linear 线性插值、polars 默认 nearest……），
放任默认值必然跨语言对不齐。本仓库统一采用 **nearest-rank** 口径并在每个实现中显式遵守：

```
排序后取下标 ceil(p/100 * n) - 1    （整数运算：(p*n+99)/100 - 1，再夹到 [0, n-1]）
```

分位数与 Top-K 在各实现中按此口径手写；分组聚合交给各自生态库——**库做库擅长的事，
口径问题显式声明**，这也是多语言协作中最容易踩的静默不一致之一。

## API 契约

### `POST /analyze`

请求体（字段均可省略，走默认值）：

```json
{ "rows": 200000, "categories": 8 }
```

- `rows`：1000 ~ 2000000
- `categories`：1 ~ 64

响应（字段顺序即契约，耗时字段仅作参考不做跨语言断言）：

```json
{
  "rows": 200000,
  "categories": 8,
  "groups": [
    { "category": "cat-0", "count": 25000, "sum": 1249993286,
      "avg": 49999.73144, "p50": 50012, "p95": 94974 }
  ],
  "top10": [
    { "id": 43209, "category": "cat-1", "amount": 99999 }
  ],
  "gen_ms": 84, "agg_ms": 72, "elapsed_ms": 156
}
```

- `groups` 按 category 名称升序；`sum`/`p50`/`p95` 为整数（结果可被 64 位整数精确表示）
- `top10` 恰好 10 条：amount 降序，平局按 id 升序（amount 范围只有 10 万，平局必然出现，规则必须显式）
- 非法参数返回 `400` + `{"error": "..."}`

### `GET /health`

返回 `{"service":"data-analysis","lang":"...","engine":"..."}`。

## 运行方式

端口分配：Java **8140** / Go **8141** / Python **8142** / Rust **8143** / TS-Node **8144**。

### Java（tablesaw）
```bash
cd java && mvn spring-boot:run          # 默认 8140
```

### Go（gonum）
```bash
cd go && go run .                        # 默认 8141
```

### Python（pandas）
```bash
cd python && pip install -r requirements.txt
uvicorn main:app --port 8142
```

### Rust（polars）
```bash
cd rust && cargo run                     # 默认 8143
```

### TS(Node)（danfojs-node）
```bash
cd ts-node && npm install && npm run dev # 默认 8144
```

### 手动调用
```bash
curl -s -X POST localhost:8141/analyze -H 'Content-Type: application/json' \
  -d '{"rows": 200000, "categories": 8}' | python3 -m json.tool
```

## 验证方式（契约级）

```bash
python3 .wb_verify/verify_all.py 14
```

验证器内置 **Python 独立 oracle**（`oracle_data`）：按同一确定性公式重算期望的
8 组统计 + Top10，对每门语言的响应做**逐字段比对**（整数字段精确相等，
`avg` 容差 1e-9；`gen_ms/agg_ms/elapsed_ms` 仅要求存在——性能数字跨机器不可比）。

这比端口探活强一个数量级：uint64 环绕写错、分位数口径漂移、Top-K 平局规则不一致，
服务都照样能起，只有契约比对能发现。

2026-10-16 本机实测：五门语言的 groups + top10 与 oracle **逐字段一致**。

## 选型思考

### 分组聚合的"一行流"对比

| 语言 | 写法 | 行数 |
|------|------|------|
| Python | `df.groupby("category")["amount"].agg(["count","sum"])` | 1 |
| Rust | `df.lazy().group_by([col("category")]).agg([col("amount").count(), col("amount").sum()])` | 1 |
| Java | `table.summarize("amount", AggregateFunctions.count, AggregateFunctions.sum).by("category")` | 1（但读结果要遍历 Row + 猜输出列名） |
| Go | 手写 `map[int][]uint64` 分桶 + 循环累加 | ~10 |
| TS | `df.groupby(["category"]).col(["amount"]).sum()` + `.count()` | 2 |

结论：**Python/Rust 是第一梯队**（生态成熟、一行流、性能强）；Java 的 tablesaw 是"能用但生态弱势"；
Go 和 TS 则展示了"没有 DataFrame 的世界"——一切都要手写。

### 关键选型决策点

| 问题 | 答案 |
|------|------|
| **要 DataFrame 生态？** | Python(pandas) / Rust(polars) 完整；Java(tablesaw) 可用；Go/TS 无 |
| **要极致性能？** | polars（lazy + 多线程）；pandas 单线程但生态补偿 |
| **分位数口径谁说了算？** | 必须项目自己定（本仓库 nearest-rank），不能信各库默认值 |
| **Top-K 平局怎么破？** | 显式定义二级排序键（id 升序），否则五语言结果必然漂移 |
| **Danfo.js 还能选吗？** | 谨慎：已停更三年，依赖 tfjs-node 3.x（原生模块），Node 大版本升级随时可能翻车 |

### 已知坑（实测记录）

- **danfojs-node 1.2.0 在 Node 24 可安装、可运行**（2026-10-16 实测：`groupby().col().sum()`
  结果与其它语言逐字段一致，整数精度无损）——但其依赖链里有 `xlsx` 的
  **cdn.sheetjs.com tarball 直连**（不走 npm registry，国内安装耗时 10+ 分钟），
  且 `@tensorflow/tfjs-node@3.x` 原生绑定对 Node 新版本没有官方支持，属于"能用但随时会翻车"。
- **JS 没有原生 64 位整数**：本场景的 LCG uint64 环绕必须用 BigInt（比 Number 慢一个数量级），
  这是 TS 在数据生成阶段的固有语言税（场景 13 已量化过）。
- **tablesaw 的 `summarize().by()` 输出列名**是 `"Count [amount]"` 这类带空格的拼接名，
  稳妥做法是按位置/按名字模式匹配读列，别硬编码列名。
- **polars 0.5x 的构造签名变了**：`DataFrame::new(Vec<Series>)` 已成
  `new(height, Vec<Column>)`，列名也从 `&str` 变成 `PlSmallStr`。本实现用
  `DataFrame::new_infer_height(vec![Column::from(Series::new("id".into(), ...))])`，
  并把 `count()` 的结果显式 `.cast(DataType::Int64)`（其原生 dtype 是 `IdxSize`，
  随平台/版本可能是 u32 或 u64）——不 cast 就得赌版本。
- **pandas 3.x 的 groupby(sort=True) 保证按 key 升序**，但 polars 的 group_by 输出顺序不保证——
  跨语言契约必须显式排序，不能依赖库的隐式行为。

### 什么时候选谁

- **探索性分析、快速出结果** → Python + pandas，无争议
- **生产流水线、数据量大、性能敏感** → Rust + polars（或 Python 调 polars）
- **已有 JVM 技术栈、数据量中等** → Java + tablesaw（接受啰嗦）
- **Go 项目里做分析** → 手写或嵌 Python/Rust 微服务，Go 自己不是为这个设计的
- **Node 全栈** → danfojs 能顶住小规模，规模化请换语言
