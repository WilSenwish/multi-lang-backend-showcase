// Package main 场景 09：HTTP 客户端（超时 / 重试 / 熔断） — Go 实现
//
// Go HTTP Client 特点：
// 1. 标准库 http.Client + http.Transport 连接池（零依赖）
// 2. Transport 可以配置：MaxIdleConns / MaxConnsPerHost / IdleConnTimeout
// 3. 超时：DialContext（连接）/ ResponseHeaderTimeout（响应头）/ Timeout（整体）
// 4. 重试：手动实现指数退避 / hashicorp/go-retryablehttp
// 5. 熔断：手动实现 / 用 x/time/rate 或 sony/gobreaker
//
// 连接池模型：
// - Transport.MaxIdleConns：全局空闲连接上限
// - Transport.MaxConnsPerHost：每个主机最大连接
// - Transport.IdleConnTimeout：空闲连接回收（默认 90s）
// - 连接池由 Go runtime 自动管理

package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
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

const (
	listenAddr = ":8116"
	mockAddr   = ":8201" // Go 内置 mock server（每个语言不同端口，避免冲突）
)

// ==================== 熔断（手动实现，简单够用） ====================

type CircuitBreaker struct {
	mu              sync.Mutex
	failureCount    int
	threshold       int           // 失败阈值
	halfOpenAfter   time.Duration // open 后多久变 half-open
	lastFailureTime time.Time
	state           string // "closed" / "open" / "half-open"
}

func NewCircuitBreaker(threshold int, halfOpenAfter time.Duration) *CircuitBreaker {
	return &CircuitBreaker{threshold: threshold, halfOpenAfter: halfOpenAfter, state: "closed"}
}

func (cb *CircuitBreaker) Allow() bool {
	cb.mu.Lock()
	defer cb.mu.Unlock()
	switch cb.state {
	case "closed":
		return true
	case "open":
		if time.Since(cb.lastFailureTime) >= cb.halfOpenAfter {
			cb.state = "half-open"
			return true // half-open 放行一次探测请求
		}
		return false
	case "half-open":
		return true
	}
	return false
}

func (cb *CircuitBreaker) RecordSuccess() {
	cb.mu.Lock()
	defer cb.mu.Unlock()
	cb.failureCount = 0
	cb.state = "closed"
}

func (cb *CircuitBreaker) RecordFailure() {
	cb.mu.Lock()
	defer cb.mu.Unlock()
	cb.failureCount++
	cb.lastFailureTime = time.Now()
	if cb.failureCount >= cb.threshold {
		cb.state = "open"
	}
}

// ==================== HTTP Client ====================

// firstOf：指针字段缺省时取默认值（区分"没传"与"显式传 0"）。
func firstOf(p *int, def int) int {
	if p == nil {
		return def
	}
	return *p
}

// callExternal 带指数退避重试 + 熔断
// 返回的 map 键集合分三种形态（跨语言统一契约）：
//
//	成功      {status_code, latency_ms, retries, success, body_preview, url, timestamp}
//	重试耗尽  {status_code, latency_ms, retries, success, error, url, timestamp}
//	熔断中    {status_code:0, latency_ms:0, retries:0, success:false, error:"CIRCUIT_OPEN: 熔断中", url, timestamp}
func callExternal(ctx context.Context, client *http.Client, cb *CircuitBreaker, url string, maxRetries int, timeout time.Duration) (map[string]interface{}, error) {
	resp := map[string]interface{}{
		"url":         url,
		"retries":     0,
		"success":     false,
		"status_code": 0,
		"latency_ms":  0,
		"timestamp":   time.Now().Format(time.RFC3339),
	}

	// 熔断检查
	if !cb.Allow() {
		resp["error"] = "CIRCUIT_OPEN: 熔断中"
		return resp, fmt.Errorf("熔断中")
	}

	start := time.Now()
	var lastErr error
	var lastStatus int // 最后一次尝试拿到的 HTTP 状态码（网络错误时为 0）

	// 指数退避重试
	for attempt := 0; attempt <= maxRetries; attempt++ {
		if attempt > 0 {
			// 指数退避：100ms → 200ms → 400ms
			backoff := time.Duration(math.Pow(2, float64(attempt-1))*100) * time.Millisecond
			select {
			case <-ctx.Done():
				return resp, ctx.Err()
			case <-time.After(backoff):
			}
		}

		reqCtx, cancel := context.WithTimeout(ctx, timeout)
		defer cancel()

		req, err := http.NewRequestWithContext(reqCtx, "GET", url, nil)
		if err != nil {
			lastErr = err
			continue
		}

		logger.Debugw("http request", "url", url, "attempt", attempt+1)
		httpResp, err := client.Do(req)
		if err != nil {
			lastErr = err
			lastStatus = 0
			continue
		}

		// 先读 body 再判断状态码：5xx 也要消费响应体（连接才能被复用），
		// 且失败路径统一走下面的"重试耗尽"分支，不再落进成功分支。
		body, _ := io.ReadAll(httpResp.Body)
		httpResp.Body.Close()
		lastStatus = httpResp.StatusCode

		// 5xx 重试
		if httpResp.StatusCode >= 500 {
			lastErr = fmt.Errorf("HTTP %d", httpResp.StatusCode)
			if attempt < maxRetries {
				continue
			}
			break // 最后一次也失败 → 统一失败路径
		}

		// 成功（< 500）
		latency := time.Since(start)
		resp["status_code"] = httpResp.StatusCode
		resp["latency_ms"] = latency.Milliseconds()
		resp["retries"] = attempt
		resp["success"] = httpResp.StatusCode < 400
		cb.RecordSuccess()

		var parsed interface{}
		if err := json.Unmarshal(body, &parsed); err == nil {
			resp["body_preview"] = parsed
		} else {
			resp["body_preview"] = string(body)
		}
		return resp, nil
	}

	// 全部重试失败（网络错误或最后一次 5xx）
	cb.RecordFailure()
	resp["status_code"] = lastStatus // 5xx 时为真实状态码（如 500），网络错误时为 0
	resp["latency_ms"] = time.Since(start).Milliseconds()
	resp["retries"] = maxRetries
	if lastErr != nil {
		resp["error"] = lastErr.Error()
	} else {
		resp["error"] = "unknown error"
	}
	return resp, lastErr
}

// ==================== Mock Server ====================

func startMockServer() {
	mux := http.NewServeMux()
	mux.HandleFunc("/ok", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(200)
		w.Write([]byte(`{"ok":true,"service":"go-mock"}`))
	})
	mux.HandleFunc("/slow", func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(2 * time.Second)
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(200)
		w.Write([]byte(`{"ok":true,"slow":true}`))
	})
	mux.HandleFunc("/fail", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(500)
		w.Write([]byte(`{"error":"mock failure"}`))
	})

	go func() {
		logger.Infow("MockServer starting", "addr", mockAddr)
		if err := http.ListenAndServe(mockAddr, mux); err != nil {
			logger.Errorw("MockServer failed", "error", err)
		}
	}()
}

// ==================== API Handler ====================

var globalCircuitBreaker = NewCircuitBreaker(3, 10*time.Second)

func callExternalHandler(c *gin.Context) {
	var req struct {
		URL        string `json:"url"`
		TimeoutMs  *int   `json:"timeout_ms"`
		RetryTimes *int   `json:"retry_times"`
	}
	// 解码失败必须显式 400：Go 的 json.Decode 遇类型不匹配会留下零值，
	// 不检查 err 的话 {"retry_times":"abc"} 会静默按默认值执行。
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(400, gin.H{"error": "invalid json body: " + err.Error()})
		return
	}
	// 指针字段区分"缺省"与"显式 0"：retry_times=0 表示不重试，
	// 非指针 int 的零值会把"显式 0"吞成默认值（其他四门语言都接受 0）。
	url := ""
	if req.URL != "" {
		url = req.URL
	} else {
		url = fmt.Sprintf("http://localhost%s/ok", mockAddr)
	}
	timeoutMs := firstOf(req.TimeoutMs, 5000)
	retryTimes := firstOf(req.RetryTimes, 2) // 总共最多 3 次（含首次）
	if timeoutMs <= 0 {
		c.JSON(400, gin.H{"error": "timeout_ms must be positive"})
		return
	}
	if retryTimes < 0 {
		c.JSON(400, gin.H{"error": "retry_times must be >= 0"})
		return
	}

	// HTTP Client：Transport 连接池 + 分开配置超时
	transport := &http.Transport{
		MaxIdleConns:      100,
		MaxConnsPerHost:   20,
		IdleConnTimeout:   30 * time.Second,
		DisableKeepAlives: false,
	}
	client := &http.Client{
		Transport: transport,
		Timeout:   0, // 不用整体 timeout，用 context 分请求控制
	}

	resp, _ := callExternal(context.Background(), client, globalCircuitBreaker,
		url, retryTimes, time.Duration(timeoutMs)*time.Millisecond)

	c.JSON(200, resp)
}

func healthHandler(c *gin.Context) {
	c.JSON(200, gin.H{
		"service":   "http-client-go",
		"mock_port": strings.TrimPrefix(mockAddr, ":"),
		"cb_state":  globalCircuitBreaker.state,
	})
}

// ==================== main ====================

func main() {
	defer logger.Sync() // flush 日志

	startMockServer()

	// 跑 httptest（占位防止未使用）
	_ = httptest.NewServer

	r := gin.Default() // 自带 Recovery + Logger 中间件
	r.POST("/call-external", callExternalHandler)
	r.GET("/health", healthHandler)

	logger.Infow("server starting", "addr", listenAddr)
	if err := r.Run(listenAddr); err != nil {
		logger.Fatalw("server failed", "error", err)
	}
}
