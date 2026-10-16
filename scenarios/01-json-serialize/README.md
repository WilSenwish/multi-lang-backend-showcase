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
| **端口** | 8090 | 8091 | 8092 | 8093 | 8094 |
| **JSON 库** | Jackson (spring-boot-starter-json) | encoding/json (标准库) | pydantic v2 + json | serde + serde_json | JSON.stringify/parse (原生) |
| **类型系统** | 强静态 + 编译期类型擦除 | 强静态 + 编译期类型擦除 | 动态 + Pydantic 运行时校验 | 强静态 + 编译期单态化 | TS 编译期擦除 + JSON 运行时 |
| **null 处理** | `String email` 永远输出（null → "email": null） | `*string Email` 指针 → null 输出 `"email": null` | `Optional[str] = None` → `"email": null` | `Option<String>` → None 输出 `"email": null` | `null` 保留 → `"email": null`；`undefined` 跳过 |
| **空集合** | `List<Integer> scores` → `"scores": []` | `[]int scores` → `"scores": []` | `list[int] = []` → `"scores": []` | `Vec<i32>` → `"scores": []` | `[]` → `"scores": []` |
| **默认值** | Lombok Builder 手动处理 | struct 字段零值（int=0, string=""） | Pydantic 字段默认值 | Rust struct 构造器 | JS 默认值模式 |
| **字段名映射** | `@JsonProperty("name")` | struct tag `json:"name"` | Pydantic Field(alias=) / model_config | `#[serde(rename = "name")]` | JSON.stringify 不认 TS 类型 |
| **性能 (bench)** | 📊 待压测 | 📊 待压测 | 📊 待压测 | 📊 待压测 | 📊 待压测 |
| **编译期安全** | ❌（泛型类型擦除） | ❌（泛型类型擦除） | ❌（运行时校验） | ✅ serde 编译期生成代码 | ❌（TS 类型擦除） |
| **依赖大小** | SpringBoot 全家桶 (≈30MB+) | **零依赖**（标准库） | FastAPI + Pydantic + uvicorn | serde + axum | 原生，无额外 JSON 依赖 |
| **API 端点数** | 5 | 5 | 5 | 5 | 5 |
| **优势** | Spring 无缝集成，生态最全 | 零依赖，极简，标准库 | Pydantic v2 快，运行时校验 | 编译期安全，零开销 | 原生支持，性能极高 |
| **痛点 & 坑** | 默认 null 都输出，要 `@JsonInclude` 过滤 | nil slice vs 空 slice 行为不同 | 运行时校验，性能不如编译期 | Option/Result 增加代码复杂度 | null vs undefined 微妙差异 |

---

## 运行方式

### Java (端口 8090)
```bash
cd scenarios/01-json-serialize/java
mise exec -- mvn spring-boot:run
# 测试
curl -s http://localhost:8090/demo | jq .
curl -s -X POST http://localhost:8090/serialize -H 'Content-Type: application/json' -d '{"hello":"world"}' | jq .json
curl -s http://localhost:8090/bench | jq '{language, total_time_ms, avg_time_us}'
```

### Go (端口 8091)
```bash
cd scenarios/01-json-serialize/go
go run main.go
# 测试
curl -s http://localhost:8091/demo | jq .
curl -s http://localhost:8091/bench | jq '{language, total_time_ms, avg_time_us}'
```

### Python (端口 8092)
```bash
cd scenarios/01-json-serialize/python
pip install -r requirements.txt
uvicorn main:app --port 8092
# 测试
curl -s http://localhost:8092/demo | jq .
curl -s http://localhost:8092/bench | jq '{language, total_time_ms, avg_time_us}'
```

### Rust (端口 8093)
```bash
cd scenarios/01-json-serialize/rust
cargo run
# 测试
curl -s http://localhost:8093/demo | jq .
curl -s http://localhost:8093/bench | jq '{language, total_time_ms, avg_time_us}'
```

### TS(Node) (端口 8094)
```bash
cd scenarios/01-json-serialize/ts-node
npm install && npm run dev
# 测试
curl -s http://localhost:8094/demo | jq .
curl -s http://localhost:8094/bench | jq '{language, total_time_ms, avg_time_us}'
```

### 批量压测（所有服务都启动后）
```bash
echo "=== 5 语言 JSON bench 对比 ==="
for port in 8090 8091 8092 8093 8094; do
  echo "--- port $port ---"
  curl -s http://localhost:$port/bench | jq '{language, total_time_ms, avg_time_us, json_size_bytes}'
done
```

---

## 统一 API 契约

5 个端点完全对齐：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/demo` | 返回标准测试 JSON（含 null/空数组/嵌套对象） |
| POST | `/serialize` | 接收 JSON → 序列化成字符串 → 返回 `{json, bytes, time_us, pretty}` |
| POST | `/deserialize` | 接收 `{json_string: "..."}` → 返回 `{parsed, time_us, size}` |
| POST | `/roundtrip` | 往返保真：serialize → deserialize → serialize → 返回 `{equal}` |
| GET | `/bench` | 10000 次循环 → 返回 `{language, iterations, total_time_ms, avg_time_us}` |

### 契约级断言（验证器逐字段 / 逐字节比对）

判定强度已从"端口监听"升级为契约级，五门语言必须同时满足：

1. **`/demo` 精确相等**：7 个字段逐一比对（含 `email: null`、`scores: []`、嵌套 `address`），键集合也必须完全相同。
2. **`/serialize` 规范序列化形式**：`json` 字段必须等于契约规定的规范字符串 ——
   **紧凑分隔符、非 ASCII 不转义、HTML 字符（`<` `>` `&`）不转义**；
   `bytes` 必须等于该字符串的 UTF-8 字节数；`pretty` 必须能解析回同一对象。
3. **`/deserialize` 语义 + 口径**：`parsed` 与输入载荷深度相等；`size` 的契约口径是
   **UTF-8 字节数**（Go `len()` / Java `getBytes().length()` / Rust `String::len()` /
   TS `Buffer.byteLength()` 天然就是字节数；Python `len(str)` 是字符数、TS `string.length`
   是 UTF-16 单元数，含非 ASCII 时会偏小，实现侧已显式换算）。
4. **`/roundtrip` 往返保真**：`equal` 必须为 `true`，`original_json` 与 `roundtrip_json`
   都必须等于规范字符串，两个 `bytes` 字段等于字节数。
5. **`/bench` 字段自洽**：`iterations == 10000`；`json_size_bytes` 必须等于 `/demo`
   对象规范序列化后的字节数（与 `/demo` 响应体交叉验证，防止"计数对、内容错"）。

> **键序说明**：Go 的 `map` 与 Rust 的 `BTreeMap` 按键名排序输出，Python / Java / TS
> 保留输入顺序。因此验证器的测试载荷**键名按字母序排列**，五门语言的 `json`
> 字符串才能逐字节比对；这不是把差异"藏起来"，而是让载荷对排序差异免疫。

### 加强验证时发现并修正的跨语言偏差

| 语言 | 偏差 | 修正 |
|------|------|------|
| Go | `json.Marshal` / `MarshalIndent` 默认把 `<` `>` `&` 转义成 `\u003c` 等 | 改用 `json.Encoder` + `SetEscapeHTML(false)`（新增 `encodeJSON` 辅助函数） |
| Python | `json.dumps` 默认 `ensure_ascii=True`，非 ASCII 变 `\uXXXX`；默认分隔符带空格 | `/serialize`、`/roundtrip`、`/bench` 统一 `ensure_ascii=False, separators=(",", ":")` |
| Python | `/deserialize` 的 `size` 用 `len(str)`（字符数） | 改为 `len(json_string.encode("utf-8"))` |
| TS-Node | `/deserialize` 的 `size` 用 `string.length`（UTF-16 单元数） | 改为 `Buffer.byteLength(json_string)` |

这些偏差在"端口监听"级判定下全部不可见 —— 服务起得来、HTTP 200、字段名一个不差，
只有把响应体拉到字节级比对才会暴露。

---

## 选型思考

### 五种 JSON 库定位

| 语言 | 场景定位 | 推荐程度 |
|------|---------|---------|
| **Go encoding/json** | 零依赖极简项目、Go 服务内部序列化 | ⭐⭐⭐⭐⭐ 够用就用标准库 |
| **Rust serde** | 对类型安全有强迫症、编译期不想出错 | ⭐⭐⭐⭐⭐ 最接近"安全即正确" |
| **TS Node 原生 JSON** | Node 后端、BFF 层、全栈一体 | ⭐⭐⭐⭐⭐ 原生最快，zod 补运行时校验 |
| **Python Pydantic** | FastAPI 项目、AI Agent API 层、需要运行时校验 | ⭐⭐⭐⭐ v2 性能大幅提升 |
| **Java Jackson** | Spring 生态、大型企业项目 | ⭐⭐⭐⭐⭐ 默认选择，生态最全 |

### 关键选型决策点

- **是否需要编译期类型安全？** → Rust serde 是唯一选择（Java/Go 泛型都擦除）
- **是否需要运行时校验？** → Python Pydantic / TS zod（Java Bean Validation 也行）
- **是否追求最小依赖？** → Go（零依赖）> TS（原生）> Rust（serde 很轻）
- **项目本身是什么语言？** → 跟随项目主流技术栈，不要跨语言引入 JSON 库

### Java 开发者踩坑

- Jackson 默认 null 全输出，线上日志里一大堆 `"field": null` 很烦 → `@JsonInclude(Include.NON_NULL)` 配置一下
- Go 零依赖很爽但泛型类型擦除让你编译期拿不到字段类型 → Go 1.18 引入泛型但也擦除
- Rust `Option<T>` 很好但写惯 Java 的 Optional 再写 Rust 的 Option，match 匹配的心智转换需要适应

