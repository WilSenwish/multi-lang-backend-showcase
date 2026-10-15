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
| **测试框架** | | | | | |
| **Mock 能力** | | | | | |
| **覆盖率** | | | | | |
| **TDD 友好度** | | | | | |
| **编译期检查** | | | | | |
| **优势** | | | | | |
| **痛点 & 坑** | | | | | |

---

## 运行方式

<!-- TODO: 实现后补充启动/运行命令 -->

### Java
```bash
mvn test
mvn jacoco:report
```

### Go
```bash
go test -v -race -cover ./...
```

### Python
```bash
pytest -v --cov=.
```

### Rust
```bash
cargo test
cargo tarpaulin
```

### TS(Node)
```bash
npm test
npm run coverage
```

---

## 选型思考

<!-- TODO: 实现后补充选型建议 -->

