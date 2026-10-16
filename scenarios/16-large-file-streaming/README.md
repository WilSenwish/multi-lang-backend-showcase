# 场景 16：大文件流式处理（large-file-streaming）

> 一句话：**"内存上限"能不能变成可断言的契约？**
> 五门语言都能起服务、都返回 200、摘要都算对 —— 只有把「RSS 增量」也纳入契约，
> "有没有真的流式"才第一次从"代码看起来像"变成"跑出来证明"。

端口：`java 8150` / `go 8151` / `python 8152` / `rust 8153` / `ts-node 8154`

---

## 1. 这个场景想突出的选型差异

"读一个大文件做转换"是最常见的后端任务之一，也是最容易悄悄写错的：

- `Files.readString()` / `f.read()` / `fs.readFile()` 都是**一次读全**的语义，
  写起来最省事，数据量一大就 OOM；
- 换成流式之后，真正的难点不是"读"，而是**行边界**：块边界不等于行边界，
  一行被切成两半时必须有地方存那半行；
- 更隐蔽的是**每行分配**：即使用了流式 IO，如果每行都 `split()` 出一个 String/数组，
  省下的内存会被垃圾回收压力重新吃回去。

本场景把这三点都变成可断言的字段。

---

## 2. 统一契约

### `POST /stream/process`

请求：

| 字段 | 默认 | 说明 |
|---|---|---|
| `size_mb` | 32 | 处理的数据量（生成 + 处理都在服务端完成，仓库里不放大文件） |
| `chunk_kib` | 64 | 读/写的固定缓冲大小（KiB） |
| `min_amount` | 50000 | 过滤阈值：只输出 `amount >= min_amount` 的行 |

响应（五门语言逐字一致）：

| 字段 | 说明 |
|---|---|
| `size_mb` / `chunk_kib` / `min_amount` | 回显请求 |
| `bytes_read` / `lines_read` | 读入的字节数 / 行数 |
| `bytes_written` / `lines_written` | 输出的字节数 / 行数 |
| **`output_file_bytes`** | **输出文件的真实大小**（`stat` 出来，不是计数器） |
| `checksum` / `output_checksum` | 输入/输出各自 SHA-256 的前 8 字节 hex |
| `chunks` | 读块次数，应等于 `ceil(bytes_read / chunk_bytes)` |
| `gen_ms` / `proc_ms` / `elapsed_ms` / `throughput_mb_s` | 耗时（跨机器不可比，只验存在性） |
| `rss_before_bytes` / `rss_peak_bytes` / **`rss_delta_bytes`** | 处理前后的进程 RSS |
| `peak_heap_bytes` / `heap_metric` | 语言特定的堆口径（**口径各不相同，见 §5**） |
| `cleanup` | 两个临时文件是否已删除 |

### 数据流（确定性，五门语言逐位一致）

```
行 i（定长 10 字节）：  "%03d,%05d\n" % (i % 1000, amount)
   amount(i) = ((i+1) * 6364136223846793005 + 1442695040888963407) mod 2^64 >> 32 % 100000
   —— 实现时用"增量加法"迭代：h += MULT（uint64 自然环绕），无需大整数库

输出行（定长 11 字节）：  "%03d,%06d\n" % (i % 1000, amount * 2)   // amount*2 可能 6 位
   —— 仅当 amount >= min_amount
```

定长行是刻意的：它让"块边界落在行中间"成为必然（`chunk` 不是 10 的倍数），
同时让 oracle 可以只算一遍就同时得到多个 `size_mb` 的摘要（小 size 是大 size 的前缀）。

---

## 3. 验证器怎么判（`.wb_verify/verify_all.py`，`kind=stream`）

三个用例：

| 用例 | 参数 | 抓的是什么 |
|---|---|---|
| 8MB / 1KiB 块 | 8192 个块 | 行几乎必然跨块 → **残余行拼接**是否正确 |
| 8MB / 64KiB 块 | 128 个块 | 同一份数据换块大小，**摘要必须完全一致**（与缓冲大小无关） |
| 32MB / 64KiB 块 | 512 个块 | 数据量 4 倍，RSS 增量不得超过 **16 MiB** |

外加两条：

- `output_file_bytes == bytes_written` —— 防止"计数器递增但内容没真正写出"
  （TS 侧第一版就踩了这个坑：`Buffer.copy()` 之后忘了推进写指针，
  6 位数字把刚拷进去的 `"NNN,"` 覆盖掉，**计数对、内容错**）；
- `cleanup == true` —— 临时文件必须删，否则多跑几次磁盘就满了。

> **为什么内存断言是必须的**：见 §6 的对照实验 —— 一次性读入的实现
> **摘要完全正确、HTTP 照样 200**，只有 `rss_delta_bytes` 暴露了它。

---

## 4. 五门语言的写法对比

| | 读原语 | 行边界 | 每行分配 | RSS 怎么拿 |
|---|---|---|---|---|
| **Go** | `os.File.Read` 读进调用方 `[]byte` | 手写 `pending` 残余拼接 | 手写数字解析/格式化 | `syscall.Getrusage` → `ru_maxrss`（真峰值） |
| **Rust** | `Read::read` + 自己循环填满 | `Vec<u8>` + `drain` 残余 | `&[u8]` 切片，默认零分配 | `libc::getrusage`（真峰值） |
| **Java** | `InputStream.readNBytes`（自带填满） | 手写 `byte[]` 残余 | 手写解析，全程不建 String | **无标准 API** → fork `ps` 采样 |
| **Python** | `os.open` + `os.read` 循环填满 | `bytearray` + `del pending[:start]` | 预生成查表避免每行 `%` | `resource.getrusage`（真峰值） |
| **TS(Node)** | `fs.readSync(fd, buf, off, len, pos)` | `Buffer` + `copy` 残余 | 手写字节解析（BigInt 生成慢） | `process.memoryUsage().rss` **轮询采样** |

几条值得记住的差异：

1. **Go 的 `Read` 不保证读满，Java 的 `readNBytes` 保证** ——
   在 Go/Rust/Python/Node 里都得自己写"填满一个块"的循环，漏了就会把短读当成 EOF，
   而这在"块大小恰好整除文件大小"时是测不出来的。
2. **Java 拿不到 RSS**：`OperatingSystemMXBean` 只有"已提交虚拟内存"，
   和常驻集不是一回事；只能 fork 一次 `ps -o rss= -p <pid>`（单位是 KB）。
   这是本场景里 Java 唯一一处比其它四门语言笨重的地方。
3. **Node 的 `heapUsed` 看不见 Buffer**：Buffer 是堆外内存，所以
   "Node 的堆没涨"根本不能证明"内存没涨"。必须看 RSS，
   而 Node 又**没有 ru_maxrss 峰值接口**，只能在循环里每 256 个块采样一次取最大值。
4. **Rust 能拿到精确的堆峰值**：`#[global_allocator]` 在分配器层计数，
   是这里唯一一个"逐字节精确"的堆指标（其余四门都是运行时估计或采样）。
5. **TS 没有 64 位整数**：数据序列只能用 `BigInt`，比 `Number` 慢一个量级 ——
   这也是本场景 TS 耗时偏高的一个来源（另一个是轮询采样 RSS）。

---

## 5. 实测结果（本机 2026-10-16，五门语言 5/5 全绿）

`rows` 口径：`size_mb=32` → 3,355,443 行 / 33,554,430 字节读入、18,454,931 字节写出。

| 语言 | 8MB/1KiB | 8MB/64KiB | 32MB/64KiB | RSS 增量（32MB 用例） | `peak_heap_bytes`（口径） |
|---|---|---|---|---|---|
| Go | 65ms | 34ms | 122ms | 0.2 MiB | 0.75 MB（`runtime.MemStats.HeapAlloc`） |
| Java | 136ms | 108ms | 427ms | 0.0 MiB | 24.4 MB（`MemoryMXBean.HeapMemoryUsage.used`） |
| Python | 545ms | 500ms | 1911ms | 1.2 MiB | 71 MB（= RSS，无廉价堆字节口径） |
| Rust（debug） | 891ms | 836ms | 3350ms | 0.0 MiB | 0.33 MB（**`global_allocator` 精确计数**） |
| Rust（release） | 63ms | 50ms | 198ms | 0.25 MiB | 0.33 MB（同上） |
| TS-Node | 164ms | 117ms | 366ms | 0.2 MiB | 20.4 MB（`heapUsed`，**不含 Buffer 堆外**） |

> 验证器统一用 `cargo run`，所以正式结果里 Rust 是 **debug** 构建那一列；
> release 那一列是单独用 `cargo build --release` + 直接跑二进制实测的
> （`target/release/large-file-streaming`）。两者差 ~17 倍 —— **读耗时前先确认构建档位**，
> 这是跨语言对比里最容易误读的一处。
> 同理，Java 的 RSS 增量显示 0.0 MiB 是 `ps` 以 KB 为单位的采样粒度所致，不代表"一点没涨"。

**关键读数**：数据量从 8MB 涨到 32MB（4 倍），五门语言的 RSS 增量**都没有随之上涨** ——
这正是"流式"的定义。

---

## 6. 对照实验：非流式实现会怎样

为了确认"内存上限断言"不是个摆设，把 Python 版改成一次性读入
（`/tmp` 下的一次性脚本，不入库）后重跑同样的数据：

| 数据量 | 流式（本仓库） | 一次性读入（`f.read()` + `split()`） |
|---|---|---|
| 8MB | 0.3 MiB | **118.3 MiB** |
| 32MB | 1.2 MiB | **382.6 MiB** |

而**一次性读入版本的 `checksum` 完全正确、HTTP 照样返回 200** ——
如果验证器只比摘要，这两版实现无法区分。这就是 §3 里 `rss_delta_bytes <= 16MiB`
存在的唯一理由。

顺带一个数字：一次性读入版把 32MB 数据切成了 335 万个 `bytes` 对象，
RSS 增量 382 MiB ≈ 数据的 12 倍。**内存爆炸的主因往往不是数据本身，而是"每行一个对象"。**

---

## 7. 选型结论

| 场景 | 舒服 | 难受 | 难受在哪 |
|---|---|---|---|
| 固定内存地处理超大文件 | **Go / Rust** | Python / TS / Java | Python/TS 的标准库默认语义就是"一次读全"，退回"自己管缓冲"这一层要写不少代码；Java 不至于 OOM，但默认写法（每行 String）的 GC 压力随数据量线性增长，且**拿不到 RSS** 只能 fork `ps` |

翻车方的补救方案与成本（都写进代码里了）：

- **Python**：必须退回 `os.open` + `os.read` + `bytearray` 手动缓冲；
  为了不掉进解释器开销，还要把"每行格式化"换成预生成查表（本场景用了 1000 + 100000 两张表）。
  代价：代码量与 Go 版相当，耗时仍是 Go 的 ~15 倍。
- **TS(Node)**：必须放弃 `createReadStream`（它的 `highWaterMark` 是隐藏缓冲），
  改用 `readSync` + 显式 position；序列生成只能上 `BigInt`；
  内存观测只能轮询采样。代价：代码最啰嗦，且"内存没问题"这件事的**证据强度最弱**。
- **Java**：`readNBytes` 省了填满循环，但必须手写数字解析/格式化来消灭每行分配；
  RSS 只能 fork `ps`。代价：JVM 堆基线本来就在 20MB 量级，"省内存"这件事在 Java 上
  收益最不直观 —— 真正划算的是**GC 压力**而不是 RSS。

---

## 8. 已知坑（本场景踩过）

- **`Buffer.copy()` 不推进写指针**（TS）：`pending.copy(outBuf, outLen, ...)` 之后
  必须 `outLen += 4`，否则后续写入会覆盖刚拷进去的内容。
  症状是"计数全对、摘要错"，只有 `output_file_bytes` 与摘要能抓到。
- **`Buffer.indexOf(10, start)` 会搜到缓冲区的未初始化尾部**（TS）：
  pending 缓冲区只有前 `pendingLen` 字节有效，必须手写扫描循环限定上界。
- **`Read` 不保证读满**（Go/Rust/Python/Node）：必须自己循环填满一个块；
  否则短读会被当成 EOF（在块大小整除文件大小时还测不出来）。
- **`ru_maxrss` 单位不一致**：Linux 是 KB，macOS 是 bytes，各语言实现里都要分支处理。
- **`ru_maxrss` 是"进程启动以来的峰值"**，不可重置 —— 所以 `rss_delta` 的含义是
  "本次处理有没有把 RSS 推到新高"，而不是"本次处理占用了多少"。先用小数据量预热，
  这个口径才干净（验证器就是先跑 8MB 两个用例再跑 32MB）。
- **临时文件一定要删**：`size_mb` 默认 32，跑十次就是 320MB 的垃圾留在 `/tmp`。
  `cleanup` 字段就是为了把这件事变成可断言的。
