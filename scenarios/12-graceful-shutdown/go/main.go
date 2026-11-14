// Package main 场景 12：优雅关闭（Graceful Shutdown）— Go 实现
//
// Go 优雅关闭特点（⭐⭐⭐⭐⭐ 最优雅！）：
// 1. signal.NotifyContext：一行代码捕获 SIGTERM/SIGINT
// 2. http.Server.Shutdown(ctx)：停止接收 + 等待 in-flight + 超时保护三合一
// 3. context.WithTimeout(ctx, 10*time.Second)：超时保护
// 4. defer server.Close()：资源清理
//
// 示例代码结构：
// ```go
// ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
// defer stop()
// go server.ListenAndServe()
// <-ctx.Done()                     // 等待信号
// server.Shutdown(context.WithTimeout(10*time.Second))  // 优雅关闭
// ```
// 就这几行！Go 设计最简洁优雅。
package main

import (
	"context"
	"fmt"
	"net/http"
	"os"
	"os/signal"
	"sync"
	"sync/atomic"
	"syscall"
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

const listenAddr = ":8131"

// ==================== 全局状态 ====================

var (
	inFlightCount atomic.Int64
	shuttingDown  atomic.Bool
	shutdownDone  sync.WaitGroup
)

// ==================== Handler ====================

func longTaskHandler(c *gin.Context) {
	id := inFlightCount.Add(1)
	logger.Infow("开始处理 long-task", "id", id, "in-flight", inFlightCount.Load())

	defer func() {
		inFlightCount.Add(-1)
		logger.Infow("完成 long-task", "id", id)
	}()

	// 模拟 3s 耗时
	time.Sleep(3 * time.Second)

	c.JSON(http.StatusOK, gin.H{
		"ok":            true,
		"duration_ms":   3000,
		"shutting_down": shuttingDown.Load(),
	})
}

func healthHandler(c *gin.Context) {
	body := gin.H{
		"service":      "graceful-shutdown-go",
		"shutting_down": shuttingDown.Load(),
		"in_flight":    inFlightCount.Load(),
	}

	if shuttingDown.Load() {
		c.JSON(http.StatusServiceUnavailable, body)
	} else {
		c.JSON(http.StatusOK, body)
	}
}

// ==================== main ====================

func main() {
	defer logger.Sync() // flush 日志

	fmt.Println("========================================")
	fmt.Println("场景 12：优雅关闭 — Go 实现（最优雅！）")
	fmt.Println("信号：kill -TERM <pid> 或 Ctrl+C")
	fmt.Println("========================================")

	r := gin.Default() // 自带 Recovery + Logger 中间件
	r.GET("/api/long-task", longTaskHandler)
	r.GET("/api/health", healthHandler)

	server := &http.Server{
		Addr:    listenAddr,
		Handler: r,
	}

	// ============ 优雅关闭的核心代码 ============
	// 1. 捕获信号（SIGTERM / SIGINT）
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	// 2. 启动 HTTP 服务（在 goroutine 里）
	go func() {
		logger.Infow("server starting", "addr", listenAddr)
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			logger.Fatalw("server error", "error", err)
		}
	}()

	// 3. 等待信号
	<-ctx.Done()
	logger.Infow("========================================")
	logger.Infow("[GRACEFUL SHUTDOWN] received signal", "signal", ctx.Err())
	logger.Infow("[GRACEFUL SHUTDOWN] Step 1/4: 标记 shutting_down=true")
	shuttingDown.Store(true)

	logger.Infow("[GRACEFUL SHUTDOWN] Step 2/4: 停止接收新请求")
	// Shutdown 会自动关闭监听器

	logger.Infow("[GRACEFUL SHUTDOWN] Step 3/4: 等待 in-flight 请求完成 (timeout=10s)")
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	if err := server.Shutdown(shutdownCtx); err != nil {
		logger.Warnw("[GRACEFUL SHUTDOWN] Shutdown 超时！强制关闭", "error", err)
		server.Close() // 强制关闭
	} else {
		logger.Infow("[GRACEFUL SHUTDOWN] Shutdown 成功，所有请求完成")
	}

	logger.Infow("[GRACEFUL SHUTDOWN] Step 4/4: 释放资源 (defer Close() 自动清理)")
	logger.Infow("[GRACEFUL SHUTDOWN] ✅ Shutdown complete")
	logger.Infow("========================================")

	_ = shutdownDone // 防未使用
}
