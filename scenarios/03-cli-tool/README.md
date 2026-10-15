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
| **编译速度** | | | | | |
| **二进制大小** | | | | | |
| **启动速度** | | | | | |
| **参数解析库** | | | | | |
| **退出码规范** | | | | | |
| **stdout/stderr** | | | | | |
| **优势** | | | | | |
| **痛点 & 坑** | | | | | |

---

## 运行方式

<!-- TODO: 实现后补充启动/运行命令 -->

### Java
```bash
# TODO
```

### Go
```bash
# TODO
```

### Python
```bash
# TODO
```

### Rust
```bash
# TODO
```

### TS(Node)
```bash
# TODO
```

---

## 选型思考

<!-- TODO: 实现后补充选型建议 -->

