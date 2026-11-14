// Package main 场景 10：单机内存限流 — Go 实现
//
// Go 限流特点：
// 1. golang.org/x/time/rate 是 Go 官方令牌桶实现（Ken Thompson 徒弟 Russ Cox 写的）
// 2. rate.NewLimiter(rate.Limit(qps), burst) 创建令牌桶
// 3. Allow() 零等待尝试获取令牌（非阻塞）
// 4. Wait(ctx) 阻塞等待直到有令牌（带 context 取消）
// 5. Reserve() 返回 Reservation，可以提前知道需要等多久
//
// 并发安全：rate.Limiter 内部用 atomic + channel（非阻塞路径）/ mutex（阻塞路径）
// 性能极高，比 Java ReentrantLock 快很多

package main

import (
	"fmt"
	"net/http"
	"sync/atomic"

	"github.com/gin-gonic/gin"
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
	"golang.org/x/time/rate"
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

const listenAddr = ":8121"

// ============ 全局限流器 ============

var (
	limiter          = rate.NewLimiter(1.0, 10) // QPS=1, burst=10
	totalRequests    int64
	allowedRequests  int64
	rejectedRequests int64
)

// ============ Handler ============

func write429(c *gin.Context, retryAfterMs int64) {
	retryAfterSec := retryAfterMs / 1000
	if retryAfterSec < 1 {
		retryAfterSec = 1
	}
	c.Header("Retry-After", fmt.Sprintf("%d", retryAfterSec))
	logger.Debugw("rate limit hit", "retryAfterMs", retryAfterMs)
	c.JSON(http.StatusTooManyRequests, gin.H{
		"error":          "rate limit exceeded",
		"retry_after_ms": retryAfterMs,
		"total":          atomic.LoadInt64(&totalRequests),
		"allowed":        atomic.LoadInt64(&allowedRequests),
		"rejected":       atomic.LoadInt64(&rejectedRequests),
	})
}

func heavyHandler(c *gin.Context) {
	atomic.AddInt64(&totalRequests, 1)

	// Reserve 一次：拿到令牌则 delay=0 放行；拿不到则立刻 Cancel 退还（不能白占一个未来令牌，
	// 否则每拒绝一次都把"下一次可用时间"往后推，Retry-After 会从 1s 一路涨到 15s+）。
	reservation := limiter.Reserve()
	if !reservation.OK() {
		atomic.AddInt64(&rejectedRequests, 1)
		write429(c, 1000)
		return
	}
	delay := reservation.Delay()
	if delay > 0 {
		reservation.Cancel()
		atomic.AddInt64(&rejectedRequests, 1)
		retryAfterMs := delay.Milliseconds()
		if retryAfterMs < 0 {
			retryAfterMs = 1000
		}
		write429(c, retryAfterMs)
		return
	}

	atomic.AddInt64(&allowedRequests, 1)
	logger.Debugw("rate limit passed")

	c.JSON(http.StatusOK, gin.H{
		"ok":       true,
		"endpoint": "/api/heavy",
		"total":    atomic.LoadInt64(&totalRequests),
		"allowed":  atomic.LoadInt64(&allowedRequests),
		"rejected": atomic.LoadInt64(&rejectedRequests),
	})
}

func healthHandler(c *gin.Context) {
	c.JSON(200, gin.H{
		"service":   "rate-limit-go",
		"algorithm": "token-bucket (golang.org/x/time/rate)",
		"qps":       1.0,
		"burst":     10,
		"total":     atomic.LoadInt64(&totalRequests),
		"allowed":   atomic.LoadInt64(&allowedRequests),
		"rejected":  atomic.LoadInt64(&rejectedRequests),
	})
}

// ============ main ============

func main() {
	defer logger.Sync() // flush 日志

	fmt.Println("限流配置：QPS=1, burst=10 (每秒 1 个令牌，桶容量 10)")
	fmt.Println("快速连续请求 /api/heavy，超过 10 个后会 429")
	fmt.Println("")

	r := gin.Default() // 自带 Recovery + Logger 中间件
	r.GET("/api/heavy", heavyHandler)
	r.GET("/health", healthHandler)

	logger.Infow("server starting", "addr", listenAddr, "qps", 1.0, "burst", 10)
	if err := r.Run(listenAddr); err != nil {
		logger.Fatalw("server failed", "error", err)
	}
}
