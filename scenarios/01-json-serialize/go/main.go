package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"time"

	"github.com/gin-gonic/gin"
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
)

// ==================== zap 结构化日志初始化 ====================

// logger 全局 SugaredLogger（JSON 输出 + stdout + DEBUG 级别 + caller 信息）
var logger *zap.SugaredLogger

func init() {
	cfg := zap.NewProductionConfig()
	cfg.OutputPaths = []string{"stdout"}
	cfg.ErrorOutputPaths = []string{"stderr"}
	cfg.EncoderConfig.TimeKey = "time"
	cfg.EncoderConfig.LevelKey = "level"
	cfg.EncoderConfig.MessageKey = "msg"
	cfg.EncoderConfig.CallerKey = "caller"
	cfg.EncoderConfig.EncodeTime = zapcore.ISO8601TimeEncoder
	cfg.EncoderConfig.EncodeLevel = zapcore.LowercaseLevelEncoder
	cfg.EncoderConfig.EncodeCaller = zapcore.ShortCallerEncoder
	cfg.Level = zap.NewAtomicLevelAt(zapcore.DebugLevel) // 最低 DEBUG 级别
	cfg.Sampling = nil                                    // 关闭采样，保证 bench 等场景日志完整

	l, err := cfg.Build()
	if err != nil {
		panic(fmt.Sprintf("zap init failed: %v", err))
	}
	logger = l.Sugar()
}

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
func demoHandler(c *gin.Context) {
	c.JSON(200, demoUser())
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
func serializeHandler(c *gin.Context) {
	var body map[string]interface{}
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(400, gin.H{"error": "invalid json: " + err.Error()})
		return
	}

	start := time.Now()
	data, err := encodeJSON(body, "")
	if err != nil {
		c.JSON(500, gin.H{"error": "marshal error: " + err.Error()})
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
	c.JSON(200, resp)
}

// POST /deserialize
func deserializeHandler(c *gin.Context) {
	var body map[string]string
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(400, gin.H{"error": "invalid json: " + err.Error()})
		return
	}

	jsonStr, ok := body["json_string"]
	if !ok {
		c.JSON(400, gin.H{"error": "missing json_string field"})
		return
	}

	start := time.Now()
	var parsed interface{}
	if err := json.Unmarshal([]byte(jsonStr), &parsed); err != nil {
		c.JSON(400, gin.H{"error": "unmarshal error: " + err.Error()})
		return
	}
	elapsedUs := time.Since(start).Microseconds()

	resp := map[string]interface{}{
		"parsed":   parsed,
		"time_us":  elapsedUs,
		"size":     len(jsonStr),
	}
	c.JSON(200, resp)
}

// POST /roundtrip
func roundtripHandler(c *gin.Context) {
	var body map[string]interface{}
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(400, gin.H{"error": "invalid json: " + err.Error()})
		return
	}

	json1, err := encodeJSON(body, "")
	if err != nil {
		c.JSON(500, gin.H{"error": "marshal error: " + err.Error()})
		return
	}

	var parsed interface{}
	if err := json.Unmarshal(json1, &parsed); err != nil {
		c.JSON(500, gin.H{"error": "unmarshal error: " + err.Error()})
		return
	}

	json2, err := encodeJSON(parsed, "")
	if err != nil {
		c.JSON(500, gin.H{"error": "marshal error: " + err.Error()})
		return
	}

	resp := map[string]interface{}{
		"original_json":   string(json1),
		"roundtrip_json":  string(json2),
		"equal":           string(json1) == string(json2),
		"original_bytes":  len(json1),
		"roundtrip_bytes": len(json2),
	}
	c.JSON(200, resp)
}

// GET /bench
func benchHandler(c *gin.Context) {
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
		"language":        "go-encoding/json",
		"iterations":      iterations,
		"total_time_ms":   totalMs,
		"avg_time_us":     float64(totalMs*1000) / float64(iterations),
		"json_size_bytes": len(lastJSON),
	}
	c.JSON(200, resp)
}

func main() {
	defer logger.Sync() // flush 日志

	r := gin.Default() // 自带 Recovery + Logger 中间件
	r.GET("/demo", demoHandler)
	r.POST("/serialize", serializeHandler)
	r.POST("/deserialize", deserializeHandler)
	r.POST("/roundtrip", roundtripHandler)
	r.GET("/bench", benchHandler)

	logger.Infow("server starting", "addr", listenAddr)
	if err := r.Run(listenAddr); err != nil {
		logger.Fatalw("server failed", "error", err)
	}
}
