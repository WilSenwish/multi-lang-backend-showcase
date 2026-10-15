# 场景 01：JSON 序列化/反序列化

## 业务描述

统一输入/输出一个嵌套 JSON 对象，测试各语言序列化和反序列化的行为差异：

- 序列化：对象 → JSON 字符串
- 反序列化：JSON 字符串 → 强类型对象
- 对比测试点：**null 值处理、空集合、默认值、嵌套对象、数组、字段名映射**

### 测试用 JSON 结构

```json
{
  "id": 1,
  "name": "Alice",
  "email": null,
  "age": 28,
  "tags": ["engineer", "java"],
  "address": {
    "city": "Beijing",
    "zip": "100000"
  },
  "scores": []
}
```

所有语言实现**业务逻辑完全一致**。

---

## 实现清单

| 语言 | JSON 库 | 备注 |
|------|---------|------|
| Java | Jackson (`spring-boot-starter-json`) | Spring 默认 |
| Go | 标准库 `encoding/json` | 零依赖 |
| Python | Pydantic v2 + `model_dump` / `model_validate` | 运行时校验 |
| Rust | serde + `#[derive(Serialize, Deserialize)]` | 编译期 |
| TS(Node) | `JSON.stringify` + `JSON.parse` + zod | 原生 + 运行时校验 |

---

## 关键对比

| 维度 | Java | Go | Python | Rust | TS(Node) |
|------|------|----|--------|------|----------|
| **类型系统** | 强静态 | 强静态 | 动态（Pydantic 运行时） | 强静态编译期 | 渐进式类型（zod 运行时） |
| **null 处理** | | | | | |
| **空集合** | | | | | |
| **默认值** | | | | | |
| **字段名映射** | | | | | |
| **性能** | | | | | |
| **错误处理** | | | | | |
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

