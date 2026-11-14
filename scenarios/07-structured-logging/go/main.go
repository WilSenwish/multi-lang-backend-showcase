// Package main 场景 07：结构化日志 — Go 实现（zap）
//
// Go 结构化日志特点：
// 1. zap（uber-go/zap）是 Go 生态主流结构化日志库，零分配、极快
// 2. Go 1.21+ 也有标准库 slog，但 zap 性能更好
// 3. zap 用 Sugar 模式（zap.SugaredLogger）方便写 %v 格式化，或 Structured 模式严格类型
// 4. context.Context 传 requestId 等链路字段，和 Go 的 concurrency 模型契合
//
// 和 Java 对比：
// - Go 没有 MDC 机制，要把 requestId 放在 context 里层层传递
// - zap 的 Field 是强类型（String / Int / Duration），编译期检查
// - zap 没有 caller 自动信息（要额外 AddCaller）
// - 性能远好于 Java（原生 + 零分配）
package main

import (
	"context"
	"crypto/rand"
	"fmt"
	"log"
	"net/http"
	"strconv"
	"sync"
	"time"

	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
)

const listenAddr = ":8106"

// 全局 logger（生产配置：JSON 输出到 stdout）
var sugar *zap.SugaredLogger

// RequestContext 持有请求级别的日志字段
type RequestContext struct {
	RequestID string
	UserID    string
	Path      string
}

// contextKey 定义 context 的 key 类型（避免 key 冲突）
type contextKey struct{}

// requestCtxKey 用于在 context 里存取 RequestContext
var requestCtxKey = contextKey{}

// withRequestContext 把 RequestContext 放进 context
func withRequestContext(ctx context.Context, rc *RequestContext) context.Context {
	return context.WithValue(ctx, requestCtxKey, rc)
}

// getRequestContext 从 context 取出 RequestContext
func getRequestContext(ctx context.Context) *RequestContext {
	if v, ok := ctx.Value(requestCtxKey).(*RequestContext); ok {
		return v
	}
	return &RequestContext{UserID: "unknown"}
}

// logFromContext 从 context 取 RequestContext，附加结构化字段
func logFromContext(ctx context.Context) *zap.SugaredLogger {
	rc := getRequestContext(ctx)
	return sugar.With(
		zap.String("requestId", rc.RequestID),
		zap.String("userId", rc.UserID),
		zap.String("path", rc.Path),
	)
}

// generateRequestID 生成 8 位十六进制短 ID（与 Java/Python/Rust/TS 一致：
// UUID 取前 8 位；之前用 UnixNano 拼出 16 位，跨语言不一致）
func generateRequestID() string {
	buf := make([]byte, 4)
	if _, err := rand.Read(buf); err != nil {
		// crypto/rand 失败时退化为时间戳低 32 位（仅兜底，正常不会走到）
		return fmt.Sprintf("%08x", time.Now().UnixNano()&0xFFFFFFFF)
	}
	return fmt.Sprintf("%x", buf)
}

// methodGuard 方法不匹配返回 405（net/http 的 ServeMux 不区分方法，
// 不显式检查的话 POST /ping 也会 200，与其余四门的 405 不一致）
func methodGuard(w http.ResponseWriter, r *http.Request, allow string) bool {
	if r.Method != allow {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusMethodNotAllowed)
		fmt.Fprintf(w, `{"error":"method not allowed"}`)
		return false
	}
	return true
}

// ==================== Handler ====================

func pingHandler(w http.ResponseWriter, r *http.Request) {
	if !methodGuard(w, r, http.MethodGet) {
		return
	}
	start := time.Now()
	rc := &RequestContext{
		RequestID: generateRequestID(),
		UserID:    "anonymous",
		Path:      "/ping",
	}
	ctx := withRequestContext(r.Context(), rc)
	logger := logFromContext(ctx)

	logger.Info("ping request handled")
	logger.Infow("request completed",
		"costMs", time.Since(start).Milliseconds(),
	)

	w.Header().Set("Content-Type", "application/json")
	fmt.Fprintf(w, `{"pong":true,"request_id":"%s"}`, rc.RequestID)
}

func debugHandler(w http.ResponseWriter, r *http.Request) {
	if !methodGuard(w, r, http.MethodGet) {
		return
	}
	rc := &RequestContext{
		RequestID: generateRequestID(),
		UserID:    "debug-user",
		Path:      "/debug",
	}
	ctx := withRequestContext(r.Context(), rc)
	logger := logFromContext(ctx)

	// Debug 级别：zap 默认 Info 才输出，Debug 不开 — 现在已调到 DEBUG
	logger.Debugw("debug request received",
		"param1", "value1",
		"param2", 42,
	)
	logger.Info("debug endpoint hit")

	w.Header().Set("Content-Type", "application/json")
	fmt.Fprintf(w, `{"debug":true,"request_id":"%s"}`, rc.RequestID)
}

func errorHandler(w http.ResponseWriter, r *http.Request) {
	if !methodGuard(w, r, http.MethodGet) {
		return
	}
	rc := &RequestContext{
		RequestID: generateRequestID(),
		UserID:    "error-user",
		Path:      "/error",
	}
	ctx := withRequestContext(r.Context(), rc)
	logger := logFromContext(ctx)

	// 故意模拟错误
	err := fmt.Errorf("nil pointer dereference on 'nullStr'")
	// Error 级别：带 zap.Error 字段会把错误消息 + 栈嵌入 JSON
	logger.Errorw("request failed with exception",
		"costMs", 150,
		"errorCode", "NULL_POINTER",
		zap.Error(err),
		zap.Stack("stacktrace"), // 完整 Go 调用栈
	)

	w.Header().Set("Content-Type", "application/json")
	fmt.Fprintf(w, `{"error":"simulated"}`)
}

func benchHandler(w http.ResponseWriter, r *http.Request) {
	if !methodGuard(w, r, http.MethodGet) {
		return
	}
	// count 缺省 1000；非数字或 < 1 都是客户端错误 → 400
	// （之前是"解析失败静默用 1000"，非法输入被悄悄吞掉）
	count := 1000
	if c := r.URL.Query().Get("count"); c != "" {
		n, err := strconv.Atoi(c)
		if err != nil || n < 1 {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusBadRequest)
			fmt.Fprintf(w, `{"error":"count must be an integer >= 1"}`)
			return
		}
		count = n
	}

	rc := &RequestContext{
		RequestID: generateRequestID(),
		UserID:    "bench-user",
		Path:      "/bench",
	}
	ctx := withRequestContext(r.Context(), rc)
	logger := logFromContext(ctx)

	start := time.Now()

	// 并发写日志测试
	var wg sync.WaitGroup
	for i := 0; i < count; i++ {
		wg.Add(1)
		go func(idx int) {
			defer wg.Done()
			logger.Infow("benchmark log entry",
				"index", idx,
				"total", count,
			)
		}(i)
	}
	wg.Wait()

	cost := time.Since(start)
	avgLogNs := cost.Nanoseconds() / int64(count)

	logger.Infow("benchmark completed",
		"count", count,
		"totalCostMs", cost.Milliseconds(),
		"avgLogNs", avgLogNs,
	)

	w.Header().Set("Content-Type", "application/json")
	fmt.Fprintf(w, `{"count":%d,"total_cost_ms":%d,"avg_log_ns":%d,"request_id":"%s"}`,
		count, cost.Milliseconds(), avgLogNs, rc.RequestID)
}

// ==================== main ====================

func main() {
	// 生产配置：JSON 格式 + stdout + caller 信息
	cfg := zap.NewProductionConfig()
	cfg.OutputPaths = []string{"stdout"}
	cfg.ErrorOutputPaths = []string{"stderr"}
	cfg.EncoderConfig.TimeKey = "time"
	cfg.EncoderConfig.LevelKey = "level"
	cfg.EncoderConfig.MessageKey = "msg"
	cfg.EncoderConfig.CallerKey = "caller"
	cfg.EncoderConfig.StacktraceKey = "stacktrace"
	cfg.EncoderConfig.EncodeTime = zapcore.ISO8601TimeEncoder
	cfg.EncoderConfig.EncodeLevel = zapcore.LowercaseLevelEncoder
	cfg.Level = zap.NewAtomicLevelAt(zapcore.DebugLevel) // 调到 DEBUG 级别
	cfg.Sampling = nil                                    // 关闭采样

	l, err := cfg.Build()
	if err != nil {
		log.Fatalf("zap init failed: %v", err)
	}
	defer l.Sync()
	sugar = l.Sugar().With(zap.String("app", "structured-logging-go"))

	sugar.Infow("server starting",
		"addr", listenAddr,
		"mode", "prod",
		"level", "DEBUG",
	)

	mux := http.NewServeMux()
	mux.HandleFunc("/ping", pingHandler)
	mux.HandleFunc("/debug", debugHandler)
	mux.HandleFunc("/error", errorHandler)
	mux.HandleFunc("/bench", benchHandler)

	if err := http.ListenAndServe(listenAddr, mux); err != nil {
		sugar.Fatal("server failed", zap.Error(err))
	}
}
