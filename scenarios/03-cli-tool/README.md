# 场景 03：命令行工具开发

## 业务描述

实现一个简化版的 **`wc` (word count)** 命令行工具，统计文件的行数、词数、字符数。

### 统一接口

```bash
# 用法
count [选项] [文件...]

# 选项
-l    只统计行数 (lines)
-w    只统计词数 (words)  
-c    只统计字符数 (chars)
-h    帮助信息

# 示例
count -l -w ./file.txt
# 输出: lines=42 words=133

count -c ./file.txt
# 输出: chars=890
```

所有语言实现**业务逻辑完全一致**。

### 统计口径（5 种语言必须对齐）

| 指标 | 口径 | 说明 |
|------|------|------|
| `lines` | **逻辑行数**：换行符个数；末行无换行时再 +1 | 对以换行结尾的文件等于 `wc -l`；对"末行无换行"的文件，`wc -l` 会少算 1 行（`wc -l` 数的是换行符） |
| `words` | 按空白（空格 / 制表 / 换行）切分后的非空字段数 | 等价于 Go `strings.Fields`、Python `str.split()`、Rust `split_whitespace()` |
| `chars` | **Unicode 码点数**（Java 例外：UTF-16 单元数） | 见下方实测差异 |

实测（输入 `a😀b\n`，即 1 个 emoji）：

```
python/ts-node/go/rust : chars=4   (码点：a、😀、b、\n)
java                   : chars=5   (UTF-16 单元：emoji 占 2 个)
```

> Java 的 `String.length()` 返回的是 UTF-16 单元数，含非 BMP 字符（emoji、部分符号）时会偏大，
> 这是 Java 字符串模型与其余四门的**固有差异**（上表「Unicode 处理」一行也标注了）。
> 其余统计值（`lines` / `words`）5 种语言必须逐字一致 —— 以仓库根 `README.md` 为输入时，
> 结果应为 `lines=206 words=777`（README 增删后数值随之变化，验证脚本每次运行都会重新计算基准）。

> 选项语义也是契约的一部分：`-l` / `-w` / `-c` 必须**各自只输出对应指标**，不传选项才三项全输出。
> 验证脚本会逐个单选项核对（曾发现 TS-Node 把选项读成 `options.l`，而 commander 实际写入的是
> `options.lines`，导致三个选项全部静默失效、怎么调都输出三项）。

---

## 实现清单

| 语言 | 参数解析库 | 构建方式 |
|------|-----------|---------|
| Java | Picocli / 手写 argparse | `java -jar` |
| Go | 标准库 `flag` | `go build` → 原生二进制 |
| Python | 标准库 `argparse` | `pyinstaller` 或直接 `python` |
| Rust | `clap` | `cargo build --release` → 原生二进制 |
| TS(Node) | `commander` / `yargs` | `tsc && node dist/` → pkg / nexe |

---

## 关键对比

| 维度 | Java | Go | Python | Rust | TS(Node) |
|------|------|----|--------|------|----------|
| **参数解析库** | Picocli | `flag`（标准库） | `argparse`（标准库） | clap (derive 宏) | commander |
| **编译方式** | Maven shade → fat-jar | `go build` → 静态二进制 | 解释执行（pyinstaller 可选） | `cargo build --release` → 静态二进制 | `tsc` → `node dist/main.js` |
| **分发形式** | `java -jar count.jar` 或 GraalVM Native Image | 直接可执行文件 | `python main.py` 或 `pyinstaller` 单文件 | 直接可执行文件 | `node main.js` 或 pkg 单文件 |
| **二进制大小 (release)** | fat-jar ≈ 5-10MB；GraalVM ≈ 15-25MB | ≈ 5-10MB | 源码 ≈ 5KB；pyinstaller ≈ 50-100MB | ≈ 2-5MB (LTO+strip) | pkg ≈ 80MB+（嵌 Node runtime） |
| **启动速度** | 慢（JVM 冷启动 ~100-500ms） | **极快**（原生 ~1-5ms） | 中（~50-200ms） | **极快**（原生 ~1-5ms） | 中（~30-100ms，Node JIT） |
| **标准库依赖** | 1 外部依赖 (picocli) | **零依赖** | 零依赖（argparse 在标准库） | 1 外部依赖 (clap) | 1 外部依赖 (commander) |
| **参数解析功能** | ⭐⭐⭐⭐⭐ 最强（子命令、互斥组、类型安全） | ⭐⭐ 基础够用 | ⭐⭐⭐⭐ 强（子命令、分组） | ⭐⭐⭐⭐⭐ 最强（clap + 类型安全） | ⭐⭐⭐⭐ 强 |
| **退出码规范** | ✅ 手动 | ✅ 手动 | ✅ `sys.exit()` | ✅ `process::exit` | ✅ `process.exit()` |
| **stdout/stderr** | ✅ 分离 | ✅ 分离 | ✅ 分离 | ✅ 分离 | ✅ 分离 |
| **Unicode 处理** | Java String 是 UTF-16 单元 | `utf8.RuneCountInString` 正确算字符 | `len()` 默认按字符 | `content.chars().count()` 正确算 Unicode | `Array.from()` 正确算字符 |
| **编译速度** | 中（Maven 下载依赖慢） | **快**（增量编译几秒） | 无编译 | 慢（cargo 首次编译） | 快（tsc 增量编译） |
| **优势** | Picocli 功能最全，和 Java 生态无缝 | 零依赖、编译快、单文件分发 | 直接写直接跑、argparse 好用 | 编译期安全、clap 类型安全、零 GC | 开发极快、TS 类型安全、npm 生态 |
| **痛点 & 坑** | JVM 冷启动慢、jar 体积大 | flag 功能有限、无子命令简写 | 分发依赖 Python、性能差 | cargo 首次编译慢、clap 宏编译耗时 | 分发依赖 Node、pkg 体积巨大 |

---

## 运行方式

### Java (fat-jar)
```bash
cd scenarios/03-cli-tool/java
mise exec -- mvn clean package -q
java -jar target/cli-tool-1.0.0.jar -l -w ../../../README.md
# 编译 GraalVM Native Image（可选，需 GraalVM）
# native-image -jar target/cli-tool-1.0.0.jar count
```

### Go (原生二进制)
```bash
cd scenarios/03-cli-tool/go
go build -o count .
./count -l -w ../../../README.md
# 交叉编译 Linux
# GOOS=linux go build -o count-linux .
```

### Python (直接运行)
```bash
cd scenarios/03-cli-tool/python
python3 main.py -l -w ../../../README.md
# 编译单文件二进制
# pip install pyinstaller
# pyinstaller --onefile main.py
```

### Rust (原生二进制)
```bash
cd scenarios/03-cli-tool/rust
cargo build --release
./target/release/count -l -w ../../../README.md
# 更极致的体积
# cargo build --release --features strip
```

### TS(Node) (node 运行 / pkg 打包)
```bash
cd scenarios/03-cli-tool/ts-node
npm install
# 方式1：tsx 直接跑 TS
npx tsx src/main.ts -l -w ../../../README.md
# 方式2：编译后 node 跑
npm run build && node dist/main.js -l -w ../../../README.md
# 方式3：pkg 打包单文件（~80MB+）
# npm i -D pkg && pkg dist/main.js --target node18-macos-x64
```

### 对比示例
```bash
# 统一统计 README.md（大约 80-120 行）
echo "=== 统一测试: count -l -w ../../../README.md ==="
echo "--- Java ---"
java -jar scenarios/03-cli-tool/java/target/cli-tool-1.0.0.jar -l -w ../../../README.md 2>/dev/null
echo "--- Go ---"
scenarios/03-cli-tool/go/count -l -w ../../../README.md
echo "--- Python ---"
python3 scenarios/03-cli-tool/python/main.py -l -w ../../../README.md
echo "--- Rust ---"
scenarios/03-cli-tool/rust/target/release/count -l -w ../../../README.md
echo "--- TS-Node ---"
cd scenarios/03-cli-tool/ts-node && npx tsx src/main.ts -l -w ../../../../README.md
```

---

## 统一 CLI 契约

5 个工具完全对齐的接口：

```bash
count [选项] <文件...>

选项:
  -l              只统计行数 (lines)
  -w              只统计词数 (words)
  -c              只统计字符数 (chars)
  -h, --help      帮助信息
  -v, --version   版本号

如果没指定任何 -l/-w/-c，默认全显示。

示例:
  count -l README.md           → lines=80
  count -l -w README.md LICENSE → lines=80 words=320  README.md
                                  lines=15  words=40   LICENSE.md
                                  ---
                                  lines=95  words=360  total

退出码:
  0 = 成功
  1 = 读取文件失败
  2 = 参数错误（argparse/clap 默认）
```

---

## 选型思考

### 五种 CLI 工具定位

| 场景 | 推荐 | 原因 |
|------|------|------|
| **要发布给别人用的高质量 CLI** | 🦀 Rust (clap) | 体积小、启动快、类型安全、无依赖 |
| **Go 项目里附带的简单 CLI** | 🐹 Go (flag) | 零依赖、和 Go 项目一体编译、分发方便 |
| **Python 脚本 + 少量 CLI 封装** | 🐍 Python (argparse) | 直接写直接跑、无编译、开发快 |
| **Node/前端项目里的工具** | 🟦 TS (commander) | 复用 npm 生态、TS 类型安全 |
| **Java 项目里的管理工具** | ☕ Java (Picocli) | 和 Spring 生态无缝、功能最全 |

### 关键选型决策点

| 问题 | 答案 |
|------|------|
| **需要单文件分发吗？** | Go / Rust 原生二进制 > Java Native Image > TS pkg > Python pyinstaller |
| **启动速度敏感吗？** | Go / Rust (~1ms) >> Python (~50ms) > Node (~80ms) > Java (~300ms) |
| **需要写复杂的子命令 / 互斥组吗？** | clap / Picocli 最强，Go flag 最弱 |
| **和现有项目集成？** | 跟随现有项目的技术栈 |
| **编译等待能接受吗？** | Rust cargo 首次编译最慢（几分钟），Go 最快（几秒） |

### Java 开发者 CLI 踩坑

- **JVM 冷启动**是硬伤 — 管理工具启动一次要 300ms，Go/Rust 1ms。写一个 `mytask.sh` 包装脚本比写 Java CLI 更实用
- **GraalVM Native Image** 能解决启动速度但编译慢、体积大（≈ 15-25MB vs Go 5MB）、且很多库不兼容
- Go 的 `flag` 够用但真的弱（不能嵌套子命令、没有互斥组）— 复杂 CLI 还是 Rust clap 更强

