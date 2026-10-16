# 场景 05：单元测试 & Mock

## 业务描述

统一测试一个简单的业务逻辑类：`OrderService`

### 被测类职责
- `calculateTotal(products: List<Product>) -> BigDecimal`：计算订单总价
- `applyDiscount(total, couponCode) -> BigDecimal`：应用优惠券折扣
- `checkout(order)`：调用外部 PaymentService（需 Mock）

### 统一测试清单

1. `calculateTotal` — 正常计算、空列表、null 产品
2. `applyDiscount` — 无优惠券、满减优惠券、折扣优惠券、无效优惠券
3. `checkout` — Mock PaymentService 成功、Mock PaymentService 抛异常

所有语言实现**测试用例完全一致**。

---

## 实现清单

| 语言 | 测试框架 | Mock 库 | 覆盖率工具 |
|------|---------|---------|-----------|
| Java | JUnit 5 | Mockito | JaCoCo |
| Go | 标准库 `testing` | 接口 + `gomock` | `go test -cover` |
| Python | pytest | `unittest.mock` | pytest-cov |
| Rust | 内置 `#[test]` + `#[cfg(test)]` | mockall | tarpaulin / cargo-llvm-cov |
| TS(Node) | Jest / Vitest | Jest mock / Sinon | Istanbul |

---

## 关键对比

| 维度 | Java | Go | Python | Rust | TS(Node) |
|------|------|----|--------|------|----------|
| **测试框架** | JUnit 5 | `testing`（标准库） | pytest | `#[test]`（标准库） | Vitest / Jest |
| **Mock 库** | Mockito | 接口 + 手写 Mock struct | `unittest.mock` | mockall (derive 宏) | sinon |
| **覆盖率工具** | JaCoCo | `go test -cover` | pytest-cov | cargo-llvm-cov / tarpaulin | c8 / istanbul |
| **Mock 方式** | 反射动态生成 | 接口注入 + 手写 struct | patch 任何函数/类 | trait + derive(Mock) | stub / spy / mock |
| **Mock 能力** | ⭐⭐⭐⭐⭐ 最强（Mock final / static 要 PowerMock） | ⭐⭐⭐⭐ 接口注入很清晰 | ⭐⭐⭐⭐⭐ 灵活（patch 一切） | ⭐⭐⭐⭐ derive 宏生成 | ⭐⭐⭐⭐⭐ sinon/Jest mock |
| **编译期检查** | ✅ 类型安全（测试代码编译检查） | ✅ 强类型编译 | ❌ 运行时才发现 | ✅ 最强 | ✅ TS 编译期 |
| **TDD 友好度** | ⭐⭐⭐⭐ JUnit 5 + Mockito | ⭐⭐⭐⭐⭐ go test 极简 + table-driven | ⭐⭐⭐⭐ pytest fixture 强 | ⭐⭐⭐ derive 宏有成本 | ⭐⭐⭐⭐ Vitest 快 |
| **运行速度** | 中（JVM 启动） | **极快**（原生） | 慢（Python 解释器） | **极快**（原生） | 中（Node JIT） |
| **真实项目常用** | JUnit 5 + Mockito | go test + gomock | pytest + pytest-cov | cargo test + mockall | Vitest/Jest + sinon |
| **优势** | 生态最全、Spring Test 无缝 | 零依赖、测试即文档 | fixture + 参数化测试简洁 | mockall 编译期生成、类型安全 | Vitest 极快、TS 无缝 |
| **痛点 & 坑** | Mock final/static 要 PowerMock | 无内置覆盖率阈值、无断言库 | 无编译期检查、跑错了才发现 | mockall 依赖 nightly proc_macro | sinon API 多、学习成本 |

---

## 统一测试清单（5 语言完全一致）

被测类：`OrderService`，3 个方法：
- `calculateTotal(products)` — 计算总价
- `applyDiscount(total, couponCode)` — 优惠券折扣
- `checkout(order)` — 调用外部 PaymentService（需 Mock）

测试用例（共 ~16 个）：

| 方法 | 用例 | 说明 |
|------|------|------|
| calculateTotal | 正常多个产品 | 10×2 + 5×3 = 35 |
| calculateTotal | 空列表 | → 0 |
| calculateTotal | null 列表 | → 0 |
| applyDiscount | 无优惠券（null/空） | 返回原价 |
| applyDiscount | SAVE50 满100减50 | ≥100 减 50 |
| applyDiscount | SAVE50 不满100 | 不减 |
| applyDiscount | DISCOUNT10 九折 | ×0.9 |
| applyDiscount | DISCOUNT20 八折 | ×0.8 |
| applyDiscount | 无效优惠券 | 报错 |
| checkout | 支付成功 | Mock pay → 返回 paymentId |
| checkout | 支付失败 | Mock pay 抛异常 |
| checkout | 空订单 | Payment 不应被调用 |
| checkout | nil 订单 | Payment 不应被调用 |

---

## 运行方式

### Java
```bash
cd scenarios/05-unit-test-mock/java
mise exec -- mvn test
# 覆盖率报告
mise exec -- mvn jacoco:report
# 打开 target/site/jacoco/index.html
```

### Go
```bash
cd scenarios/05-unit-test-mock/go
go test -v -race -cover ./...
# 覆盖率报告
go test -coverprofile=coverage.out ./... && go tool cover -html=coverage.out
# Benchmark
go test -bench=. -benchmem
```

### Python
```bash
cd scenarios/05-unit-test-mock/python
pip install -r requirements.txt
pytest -v --cov=.
# 覆盖率报告
pytest --cov=. --cov-report=html
# 打开 htmlcov/index.html
```

### Rust
```bash
cd scenarios/05-unit-test-mock/rust
cargo test
# 覆盖率（需要 cargo-llvm-cov 或 tarpaulin）
# cargo install cargo-llvm-cov && cargo llvm-cov --html
# cargo install cargo-tarpaulin && cargo tarpaulin
```

### TS(Node)
```bash
cd scenarios/05-unit-test-mock/ts-node
npm install
npm test
# 覆盖率
npm run coverage
```

### 批量跑（每个都在各自目录）
```bash
echo "=== Java ==="
cd scenarios/05-unit-test-mock/java && mise exec -- mvn -q test && cd ../../../

echo "=== Go ==="
cd scenarios/05-unit-test-mock/go && go test -v -cover ./... && cd ../../../

echo "=== Python ==="
cd scenarios/05-unit-test-mock/python && pytest -v && cd ../../../

echo "=== Rust ==="
cd scenarios/05-unit-test-mock/rust && cargo test && cd ../../../

echo "=== TS-Node ==="
cd scenarios/05-unit-test-mock/ts-node && npm test && cd ../../../
```

---

## 选型思考

### 五种测试生态定位

| 语言 | 测试框架 | Mock 库 | 覆盖率 | 推荐程度 |
|------|---------|---------|--------|---------|
| ☕ **Java** | JUnit 5 | Mockito | JaCoCo | ⭐⭐⭐⭐⭐ 企业级首选 |
| 🐹 **Go** | `testing`（零依赖） | gomock / 手写 struct | `go test -cover` | ⭐⭐⭐⭐⭐ 极简好用 |
| 🐍 **Python** | pytest | `unittest.mock` | pytest-cov | ⭐⭐⭐⭐⭐ fixture + 参数化强 |
| 🦀 **Rust** | `#[test]`（内置） | mockall | cargo-llvm-cov | ⭐⭐⭐⭐ 编译期安全，略复杂 |
| 🟦 **TS(Node)** | Vitest / Jest | sinon | c8 | ⭐⭐⭐⭐⭐ 速度快，TS 无缝 |

### 关键选型决策点

| 问题 | 答案 |
|------|------|
| **哪种测试最值得学？** | JUnit 5 / pytest / Vitest（覆盖 90% 场景） |
| **哪种 Mock 最灵活？** | Python unittest.mock（能 patch 一切）> Java Mockito > TS sinon |
| **哪种 Mock 最安全？** | Rust mockall（编译期生成）> Go 接口注入（手写） |
| **覆盖率工具哪个好？** | JaCoCo（Java 最强）> go test -cover（Go 零依赖）> c8（Node） |
| **Go 为什么不引入 testify？** | 简单场景不用，复杂场景 testify/assert/suite 好用 |

