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
| **端口** | 8095 | 8096 | 8097 | 8098 | 8099 |
| **文件 IO API** | `java.nio.file.Files` | `os` + `filepath` | `pathlib` + `os` | `std::fs` + `PathBuf` | `fs/promises` + `path` |
| **异步支持** | 同步 NIO + Spring 线程池 | 同步 + goroutine | 同步 pathlib（FastAPI 线程池） | `tokio::fs` 异步 | `fs/promises` 原生 async |
| **路径处理** | `java.nio.file.Path`（不可变） | `filepath.Join/Clean` | `pathlib.Path`（面向对象） | `PathBuf`（可变） | `path.join` |
| **编码处理** | 显式 `StandardCharsets.UTF_8` | `os.WriteFile` 默认 UTF-8 | `pathlib` 默认 UTF-8 | 显式 `.as_bytes()` | 默认 UTF-8 |
| **递归目录遍历** | `Files.walkFileTree` + Visitor | `filepath.WalkDir`（Go 1.16+） | `Path.rglob("*")` | 手动递归 `fs::read_dir` | 递归 `fs.readdir` |
| **创建目录** | `Files.createDirectories` | `os.MkdirAll` | `Path.mkdir(parents=True)` | `fs::create_dir_all` | `fs.mkdir({recursive:true})` |
| **错误处理** | Exception（try-catch） | error 返回值 | Exception（try-except） | Result<T,E>（必须处理） | Error（try-catch in async） |
| **性能** | NIO 同步快，但 Spring 线程池开销 | os 包直接，非常快 | pathlib 封装层，稍慢 | **最快**（零 GC，直接 OS 调用） | libuv 线程池异步，快 |
| **API 丰富度** | ⭐⭐⭐⭐⭐ WatchService / AttributeViews | ⭐⭐⭐⭐ 够用 | ⭐⭐⭐⭐⭐ pathlib 面向对象 | ⭐⭐⭐⭐ 够用 | ⭐⭐⭐⭐ 够用，缺 walk 原生 |
| **优势** | NIO.2 功能最全，WatchService 监听文件变更 | 零依赖，简洁直接 | pathlib 优雅，FastAPI 自动线程池 | 错误处理严格，性能极致，无 GC | 原生 async/await，ts 类型安全 |
| **痛点 & 坑** | `Files.walkFileTree` Visitor 模式啰嗦，Stream API 好 | 没有 WatchService，递归要自己写 | 递归遍历原生需要 glob/rglob | 没有 walkdir crate 要手动递归 | 原生没有递归 walk，要自己写 |

---

## 统一 API 契约（3 个端点）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/file/write` | 写文件：`{path, content, append?}` |
| GET | `/file/read?path=` | 读文件 |
| GET | `/file/scan?dir=&recursive=` | 目录遍历（默认递归=true） |

### POST /file/write
```bash
curl -s -X POST http://localhost:8095/file/write \
  -H 'Content-Type: application/json' \
  -d '{"path":"/tmp/showcase-test.json","content":{"hello":"world","data":[1,2,3]},"append":false}'
→ {"success":true,"path":"/tmp/showcase-test.json","bytes_written":42,"append":false}
```

### GET /file/read
```bash
curl -s http://localhost:8095/file/read?path=/tmp/showcase-test.json | jq .
```

### GET /file/scan
```bash
# 递归
curl -s http://localhost:8095/file/scan?dir=/tmp
# 非递归
curl -s 'http://localhost:8095/file/scan?dir=/tmp&recursive=false' | jq .
```

---

## 运行方式

### Java (端口 8095)
```bash
cd scenarios/04-file-io/java
mise exec -- mvn spring-boot:run
```

### Go (端口 8096)
```bash
cd scenarios/04-file-io/go
go run main.go
```

### Python (端口 8097)
```bash
cd scenarios/04-file-io/python
pip install -r requirements.txt
uvicorn main:app --port 8097
```

### Rust (端口 8098)
```bash
cd scenarios/04-file-io/rust
cargo run
```

### TS(Node) (端口 8099)
```bash
cd scenarios/04-file-io/ts-node
npm install && npm run dev
```

### 批量测试
```bash
# 写测试文件
echo "=== 写文件 ==="
for port in 8095 8096 8097 8098 8099; do
  curl -s -X POST http://localhost:$port/file/write \
    -H 'Content-Type: application/json' \
    -d '{"path":"/tmp/showcase-test.json","content":"{\"test\":\"'$port'\"}","append":false}' \
    | jq -c .
done
# 读测试文件
echo "=== 读文件 ==="
curl -s 'http://localhost:8095/file/read?path=/tmp/showcase-test.json' | jq .
# 扫描当前目录
echo "=== 扫描目录 ==="
curl -s 'http://localhost:8095/file/scan?dir=.' | jq .
```

---

## 选型思考

### 五种文件 IO 定位

| 场景 | 推荐 | 原因 |
|------|------|------|
| **Java 项目里的文件操作** | ☕ Java NIO.2 `Files` | WatchService 监听文件变更、AttributeViews 查属性 |
| **Go 项目里的简单文件操作** | 🐹 `os` + `filepath` | 零依赖，够用就行 |
| **Python 脚本 / AI 数据处理** | 🐍 `pathlib` | 面向对象，链式操作，写起来优雅 |
| **高性能文件服务器 / 中间件** | 🦀 Rust `std::fs` / `tokio::fs` | 无 GC，错误处理严格，性能极致 |
| **Node 后端 / BFF 层读写** | 🟦 `fs/promises` | 原生 async/await，和 TS async 无缝配合 |

### 关键选型决策点

| 问题 | 答案 |
|------|------|
| **需要监听文件变化（热重载、config watch）？** | Java WatchService 最成熟，Rust notify crate 也行，Go 用 fsnotify |
| **要做文件同步 / 备份工具？** | Rust 性能最好 + 错误处理严格 |
| **递归遍历目录找文件？** | Go walkdir / Rust walkdir / Python rglob / Node glob |
| **异步文件 IO 是必须？** | Node fs/promises / Rust tokio::fs / Python aiofiles / Java NIO.2 + AsynchronousFileChannel |
| **性能敏感（大文件、海量小文件）？** | Rust > Go > Java NIO > Node libuv > Python pathlib |

