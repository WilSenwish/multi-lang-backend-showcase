package main

import (
	"bytes"
	"encoding/json"
	"log"
	"net/http"
	"time"
)

// 统一接口（和 Java / Python / Rust / TS-Node 相同的 5 个端点）：
// GET  /demo          → 返回标准测试 JSON
// POST /serialize      → 对象 → JSON 字符串
// POST /deserialize    → JSON 字符串 → 对象
// POST /roundtrip      → 往返保真测试
// GET  /bench          → 10000 次循环性能基准
//
// Go 的 encoding/json 特点：
// 1. 零依赖，标准库自带
// 2. struct tag 控制序列化行为（`json:"fieldName,omitempty"`）
// 3. nil 指针字段默认会输出 null（除非 omitempty）
// 4. 空 slice 输出 []，nil slice 输出 null — 和 Java 不同！
// 5. 编译期类型安全（和 Rust/Java 一样，比 Python/TS 运行时校验强）

const listenAddr = ":8091"

// Address 嵌套结构
type Address struct {
	City string `json:"city"`
	Zip  string `json:"zip"`
}

// User 测试用结构
type User struct {
	ID      int       `json:"id"`
	Name    string    `json:"name"`
	Email   *string   `json:"email"` // 用指针表达 null — Go 没有 nullable 类型
	Age     int       `json:"age"`
	Tags    []string  `json:"tags"`
	Address Address   `json:"address"`
	Scores  []int     `json:"scores"` // 空 slice → 输出 []
}

// demoUser 返回标准测试对象（email 为 nil 指针 → JSON null，scores 为空 slice → JSON []）
func demoUser() User {
	return User{
		ID:      1,
		Name:    "Alice",
		Email:   nil, // nil 指针 → JSON "email": null
		Age:     28,
		Tags:    []string{"engineer", "java"},
		Address: Address{City: "Beijing", Zip: "100000"},
		Scores:  []int{}, // 空 slice → JSON "scores": []
	}
}

// ==================== 5 个 Handler ====================

// GET /demo
func demoHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	writeJSON(w, demoUser())
}

// encodeJSON 按契约序列化：紧凑分隔符 + 不转义 HTML 字符。
// Go 的 json.Marshal / json.MarshalIndent 默认会把 < > & 转义成 \u003c \u003e \u0026，
// 与另外四门语言的"标准 JSON"不一致 —— 只有 Encoder 能关掉（SetEscapeHTML(false)）。
// Encoder.Encode 会在末尾补一个换行，这里 TrimRight 掉。indent 为空串时输出紧凑形式。
func encodeJSON(v interface{}, indent string) ([]byte, error) {
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false)
	if indent != "" {
		enc.SetIndent("", indent)
	}
	if err := enc.Encode(v); err != nil {
		return nil, err
	}
	return bytes.TrimRight(buf.Bytes(), "\n"), nil
}

// POST /serialize
func serializeHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var body map[string]interface{}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		http.Error(w, "invalid json: "+err.Error(), http.StatusBadRequest)
		return
	}

	start := time.Now()
	data, err := encodeJSON(body, "")
	if err != nil {
		http.Error(w, "marshal error: "+err.Error(), http.StatusInternalServerError)
		return
	}
	elapsedUs := time.Since(start).Microseconds()

	pretty, _ := encodeJSON(body, "  ")

	resp := map[string]interface{}{
		"json":      string(data),
		"bytes":     len(data),
		"time_us":   elapsedUs,
		"pretty":    string(pretty),
	}
	writeJSON(w, resp)
}

// POST /deserialize
func deserializeHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var body map[string]string
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		http.Error(w, "invalid json: "+err.Error(), http.StatusBadRequest)
		return
	}

	jsonStr, ok := body["json_string"]
	if !ok {
		http.Error(w, "missing json_string field", http.StatusBadRequest)
		return
	}

	start := time.Now()
	var parsed interface{}
	if err := json.Unmarshal([]byte(jsonStr), &parsed); err != nil {
		http.Error(w, "unmarshal error: "+err.Error(), http.StatusBadRequest)
		return
	}
	elapsedUs := time.Since(start).Microseconds()

	resp := map[string]interface{}{
		"parsed":   parsed,
		"time_us":  elapsedUs,
		"size":     len(jsonStr),
	}
	writeJSON(w, resp)
}

// POST /roundtrip
func roundtripHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var body map[string]interface{}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		http.Error(w, "invalid json: "+err.Error(), http.StatusBadRequest)
		return
	}

	json1, err := encodeJSON(body, "")
	if err != nil {
		http.Error(w, "marshal error: "+err.Error(), http.StatusInternalServerError)
		return
	}

	var parsed interface{}
	if err := json.Unmarshal(json1, &parsed); err != nil {
		http.Error(w, "unmarshal error: "+err.Error(), http.StatusInternalServerError)
		return
	}

	json2, err := encodeJSON(parsed, "")
	if err != nil {
		http.Error(w, "marshal error: "+err.Error(), http.StatusInternalServerError)
		return
	}

	resp := map[string]interface{}{
		"original_json":   string(json1),
		"roundtrip_json":  string(json2),
		"equal":           string(json1) == string(json2),
		"original_bytes":  len(json1),
		"roundtrip_bytes": len(json2),
	}
	writeJSON(w, resp)
}

// GET /bench
func benchHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	user := demoUser()
	iterations := 10000

	// 预热
	for i := 0; i < 100; i++ {
		data, _ := json.Marshal(user)
		var parsed interface{}
		json.Unmarshal(data, &parsed)
	}

	start := time.Now()
	var lastJSON []byte
	for i := 0; i < iterations; i++ {
		lastJSON, _ = json.Marshal(user)
		var parsed interface{}
		json.Unmarshal(lastJSON, &parsed)
	}
	totalMs := time.Since(start).Milliseconds()

	resp := map[string]interface{}{
		"language":       "go-encoding/json",
		"iterations":     iterations,
		"total_time_ms":  totalMs,
		"avg_time_us":    float64(totalMs*1000) / float64(iterations),
		"json_size_bytes": len(lastJSON),
	}
	writeJSON(w, resp)
}

func writeJSON(w http.ResponseWriter, v interface{}) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(v)
}

func main() {
	mux := http.NewServeMux()
	mux.HandleFunc("/demo", demoHandler)
	mux.HandleFunc("/serialize", serializeHandler)
	mux.HandleFunc("/deserialize", deserializeHandler)
	mux.HandleFunc("/roundtrip", roundtripHandler)
	mux.HandleFunc("/bench", benchHandler)

	log.Printf("[Go] json-serialize server starting on %s", listenAddr)
	if err := http.ListenAndServe(listenAddr, mux); err != nil {
		log.Fatalf("server failed: %v", err)
	}
}
