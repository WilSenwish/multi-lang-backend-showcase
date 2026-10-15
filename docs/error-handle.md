# 错误处理专题

> Exception / error return / Result — 五门语言错误处理范式的本质差异。

---

## 1. 各语言错误处理范式

### Java：try-catch + 受检异常

```java
// 受检异常（必须处理）
try {
    file.read();
} catch (IOException e) {
    log.error("读取文件失败", e);
}

// 非受检异常（RuntimeException）
throw new IllegalArgumentException("参数错误");
```

- 受检异常强制调用方处理（争议点：Java 8+ 的 Optional 也是替代方案）
- 异常会导致调用栈展开，有性能开销
- 过度使用 try-catch 会让代码臃肿

### Go：显式 error 返回值

```go
func readFile(path string) ([]byte, error) {
    data, err := os.ReadFile(path)
    if err != nil {
        return nil, fmt.Errorf("读取文件失败: %w", err)
    }
    return data, nil
}

// 调用方必须处理
data, err := readFile("config.json")
if err != nil {
    log.Fatal(err)
}
```

- **没有 try-catch**，所有错误通过返回值传递
- `error` 是接口类型，可自定义错误类型
- `fmt.Errorf("xxx: %w", err)` 支持错误链 unwrap
- 优点：错误路径明确可见，不会被遗漏
- 缺点：样板代码多，容易忘记处理

### Python：Exception + try-except

```python
try:
    result = risky_operation()
except ValueError as e:
    print(f"值错误: {e}")
except Exception as e:
    print(f"未知错误: {e}")
else:
    print("成功")
finally:
    cleanup()
```

- 动态语言，没有编译期强制处理
- `try-except` 可以捕获任意异常层级
- 常见模式：**EAFP**（Easier to Ask for Forgiveness than Permission）
- 缺点：过度宽泛的 except 会吞掉 bug

### Rust：Result<T, E> 枚举

```rust
fn read_file(path: &str) -> Result<String, io::Error> {
    let content = fs::read_to_string(path)?;  // ? 运算符传播错误
    Ok(content)
}

// 调用方式
match read_file("config.json") {
    Ok(content) => println!("内容: {}", content),
    Err(e) => eprintln!("错误: {}", e),
}

// 或者链式处理
let content = read_file("config.json")
    .context("读取配置文件失败")?;
```

- `Result<T, E>` 是枚举：`Ok(T)` 或 `Err(E)`
- **编译期强制处理**（类似 Java 受检异常，但更优雅）
- `?` 运算符自动传播错误（需要 `From` trait）
- `anyhow` / `thiserror` crate 提供错误包装和自定义
- 优点：类型安全的错误处理，编译器帮你检查
- 缺点：学习曲线，`Box<dyn Error>` 动态分发

### TS(Node)：Exception + Promise rejection

```typescript
// 同步
try {
    doSomething();
} catch (err) {
    console.error("错误:", err);
}

// 异步 Promise
async function main() {
    try {
        await fetchData();
    } catch (err) {
        console.error("异步错误:", err);
    }
}
```

- 同步用 try-catch，异步用 try-catch 或 `.catch()`
- 运行时错误，没有编译期强制处理
- `Zod` 等库提供运行时类型校验

---

## 2. 错误处理范式对比表

| 维度 | Java | Go | Python | Rust | TS(Node) |
|------|------|----|--------|------|----------|
| 处理方式 | try-catch | error 返回 | try-except | Result 枚举 | try-catch |
| 强制处理 | 受检异常强制 | 约定强制 | 不强制 | **编译期强制** | 不强制 |
| 传播方式 | 异常抛出 | return 传递 | 异常抛出 | `?` 运算符 | throw / reject |
| 性能 | 栈展开开销 | 极低 | 栈展开开销 | 极低 | 中 |
| 类型安全 | 受检异常类型 | error 接口 | 无 | Result<E> 类型 | 无（TS 可选） |
| 错误链 | cause 链 | %w wrap | `raise X from Y` | anyhow::Context | cause (ES2022) |
| 范式偏好 | LBYL | 显式检查 | **EAFP** | 显式 + ? | EAFP |

---

## 3. Java 开发者思维定势坑

| 思维定势 | 在其他语言中 | 正确做法 |
|---------|------------|---------|
| try-catch 到处写 | Go | 每步检查 err != nil |
| 受检异常必须处理 | Python | 不一定，合理使用 EAFP |
| new RuntimeException | Rust | Err(e) / unwrap / expect |
| 异常作为流程控制 | Go/Rust | **禁止**，错误是值 |

---

## 4. 选型建议

- **微服务/基础设施**：Go / Rust 显式错误处理更适合，错误路径清晰可见
- **业务快速迭代**：Python / TS 异常处理更灵活，不被样板代码拖累
- **大型企业项目**：Java / Rust 强制错误处理保证代码质量
