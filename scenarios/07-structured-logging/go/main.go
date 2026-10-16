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

// generateRequestID 生成短 UUID
func generateRequestID() string {
	buf := make([]byte, 8)
	t := time.Now().UnixNano()
	for i := 0; i < 8; i++ {
		buf[i] = byte(t >> (i * 4))
	}
	return fmt.Sprintf("%x", buf)
}

// ==================== Handler ====================

func pingHandler(w http.ResponseWriter, r *http.Request) {
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
	rc := &RequestContext{
		RequestID: generateRequestID(),
		UserID:    "debug-user",
		Path:      "/debug",
	}
	ctx := withRequestContext(r.Context(), rc)
	logger := logFromContext(ctx)

	// Debug 级别：zap 默认 Info 才输出，Debug 不开
	logger.Debugw("debug request received",
		"param1", "value1",
		"param2", 42,
	)
	logger.Info("debug endpoint hit")

	w.Header().Set("Content-Type", "application/json")
	fmt.Fprintf(w, `{"debug":true,"request_id":"%s"}`, rc.RequestID)
}

func errorHandler(w http.ResponseWriter, r *http.Request) {
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
	count := 1000
	if c := r.URL.Query().Get("count"); c != "" {
		if n, err := strconv.Atoi(c); err == nil && n > 0 {
			count = n
		}
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

	l, err := cfg.Build()
	if err != nil {
		log.Fatalf("zap init failed: %v", err)
	}
	defer l.Sync()
	sugar = l.Sugar().With(zap.String("app", "structured-logging-go"))

	sugar.Infow("server starting",
		"addr", listenAddr,
		"mode", "prod",
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
