# Java 开发者踩坑清单

> 从 Java 转到其他 4 门语言时，常见的思维定势和反模式。带着 Java 经验来，但别让它成为你的枷锁。

---

## 1. Go 思维定势坑

| # | Java 思维 | Go 现实 | 正确做法 |
|---|----------|---------|---------|
| 1 | 创建大量线程 | Goroutine 极轻量 | 放心开 goroutine，百万级没问题 |
| 2 | synchronized/Lock 加锁 | Go 推荐 **通过通信共享内存** | 优先用 channel，简单场景用 sync.Mutex |
| 3 | try-catch 处理所有错误 | 没有 try-catch | 每步 `if err != nil { return err }` |
| 4 | 类继承 (extends) | 没有继承 | 用 **组合** + 接口 |
| 5 | 方法重载 | 不支持 | 不同方法名，或 functional options 模式 |
| 6 | 用异常做流程控制 | **禁止** | 错误是值，显式处理 |
| 7 | 空指针 NullPointerException | nil 是一等公民 | 正确初始化，或用指针判空 |
| 8 | 包管理复杂 | go mod 极简 | 放心引入新依赖，go.sum 自动生成 |

### Go 推荐阅读顺序
1. Go Tour：https://go.dev/tour/
2. Effective Go：https://go.dev/doc/effective_go
3. 100 Go Mistakes and How to Avoid Them

---

## 2. Python 思维定势坑

| # | Java 思维 | Python 现实 | 正确做法 |
|---|----------|------------|---------|
| 1 | 多线程能并行计算 | **GIL 让 CPU 密集串行** | CPU 密集用 multiprocessing，IO 密集用 asyncio |
| 2 | 强类型处处检查 | 动态类型，鸭子类型 | 合理使用 type hints，但别过度 |
| 3 | 异常要 catch 所有层 | EAFP 哲学 | 先尝试，catch 失败；不是先检查再做 |
| 4 | 接口 (interface) | 没有 interface 关键字 | 隐式接口（鸭子类型），Protocol 替代 |
| 5 | 依赖管理简单（Maven） | Python 依赖地狱 | 用 Poetry / uv，锁定版本 |
| 6 | 线程池处理一切 | asyncio 更适合 IO 密集 | FastAPI / aiohttp 基于 asyncio |
| 7 | 字节码是最终产物 | Python 需要运行时 | 部署时注意 venv 和依赖隔离 |
| 8 | OOP 是正道 | Python 函数式也很棒 | 别什么都写成类 |

### Python 推荐阅读
1. Python 官方教程：https://docs.python.org/3/tutorial/
2. The Zen of Python（输入 `import this`）
3. FastAPI 官方文档（如果做后端）

---

## 3. Rust 思维定势坑

| # | Java 思维 | Rust 现实 | 正确做法 |
|---|----------|----------|---------|
| 1 | 在线程间传对象引用 | **所有权系统不允许** | 用 `Arc<T>` / `Mutex<T>` 或消息传递 |
| 2 | GC 帮你管内存 | 没有 GC | 理解所有权、借用、生命周期 |
| 3 | 到处 clone() | clone 有成本 | 优先用引用，必要时 Arc 共享 |
| 4 | 异常处理一切 | Result 枚举 | `match` / `?` / `unwrap` / `expect` |
| 5 | 可变引用随便用 | **同时只能有一个可变引用** | 重构代码适应借用规则 |
| 6 | 空引用 NullPointerException | Option 类型 | 用 `Option<T>` 强制处理 null 情况 |
| 7 | 继承 | 没有继承 | 用组合 + trait |
| 8 | 运行时才会崩 | 编译期解决一切 | 耐心和编译器对话，它是你的朋友 |

### Rust 推荐阅读
1. The Rust Book：https://doc.rust-lang.org/book/
2. Rust 官方示例：https://doc.rust-lang.org/rust-by-example/
3. 《The Rust Programming Language》实体书

---

## 4. TS(Node) 思维定势坑

| # | Java 思维 | TS(Node) 现实 | 正确做法 |
|---|----------|--------------|---------|
| 1 | 多线程并行 | 单线程事件循环 | 天然避免数据竞争，IO 极高效 |
| 2 | synchronized/Lock | 不需要（单线程） | 用 worker_threads 处理 CPU 密集 |
| 3 | 强类型一切 | TS 是渐进式类型 | 合理使用，别让类型阻碍快速开发 |
| 4 | 依赖管理简单 | npm 幽灵依赖 | 用 pnpm，严格控制依赖 |
| 5 | 部署 JAR 包 | Node 需要运行时 | Docker 打包包含 Node 运行时 |
| 6 | 编译是必须 | JS 可以直接运行 | TS 编译后运行，或用 ts-node/tsx |
| 7 | Exception 到处 catch | 异步 Promise 有不同传播方式 | async-await 统一处理 |

---

## 5. 通用建议

### 学新语言的正确姿势

1. **先忘掉 Java 的惯用法**，按新语言的设计哲学写代码
2. **写小 Demo 跑通**，不要直接改生产代码
3. **用好编译器/Rust 编译器是老师，Go fmt/vet 是规范检查**
4. **加入社区**，看别人怎么写（GitHub 上的 star 项目）
5. **对比写同一场景**，这个仓库的做法就是最好的学习方式

### 五个语言一句话心法

| 语言 | 心法 |
|------|------|
| Java | 生态为王，约定优于配置 |
| Go | **简单至上，通信优于共享** |
| Python | **优雅优先，先用再检查 (EAFP)** |
| Rust | **编译器是队友，所有权是护城河** |
| TS(Node) | **异步第一，事件循环是核心** |
