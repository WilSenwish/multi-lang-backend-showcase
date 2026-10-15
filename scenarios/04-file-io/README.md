# 场景 04：文件读写 & 目录遍历

## 业务描述

统一实现文件系统操作：

1. **写文件**：将 JSON 内容写入文件（覆盖 + 追加模式）
2. **读文件**：读取文件内容并解析为对象
3. **目录遍历**：递归遍历目录，统计文件数量和总大小

### 统一接口（HTTP API）

```bash
# 写文件
POST /file/write
{
  "path": "/tmp/test.json",
  "content": {"data": "hello"},
  "append": false
}
→ {"success": true}

# 读文件
GET /file/read?path=/tmp/test.json
→ {"data": {...}}

# 目录遍历
GET /file/scan?dir=/tmp&recursive=true
→ {"files": 42, "total_bytes": 8900}
```

所有语言实现**业务逻辑完全一致**。

---

## 实现清单

| 语言 | IO 方案 | 异步支持 |
|------|--------|---------|
| Java | `java.nio.file` + `Files` | NIO.2 + `CompletableFuture` |
| Go | 标准库 `os` + `filepath` | 同步 API + goroutine |
| Python | 标准库 `pathlib` + `aiofiles` | asyncio + aiofiles |
| Rust | `std::fs` + `walkdir` | tokio::fs |
| TS(Node) | `fs/promises` | 原生 async/Promise |

---

## 关键对比

| 维度 | Java | Go | Python | Rust | TS(Node) |
|------|------|----|--------|------|----------|
| **同步/异步** | | | | | |
| **路径处理** | | | | | |
| **编码处理** | | | | | |
| **错误处理** | | | | | |
| **性能** | | | | | |
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

