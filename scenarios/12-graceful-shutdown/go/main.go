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
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"sync"
	"sync/atomic"
	"syscall"
	"time"
)

const listenAddr = ":8131"

// ==================== 全局状态 ====================

var (
	inFlightCount atomic.Int64
	shuttingDown  atomic.Bool
	shutdownDone  sync.WaitGroup
)

// ==================== Handler ====================

func longTaskHandler(w http.ResponseWriter, r *http.Request) {
	id := inFlightCount.Add(1)
	log.Printf("[REQUEST] 开始处理 long-task, id=%d, in-flight=%d", id, inFlightCount.Load())

	defer func() {
		inFlightCount.Add(-1)
		log.Printf("[REQUEST] 完成 long-task, id=%d", id)
	}()

	// 模拟 3s 耗时
	time.Sleep(3 * time.Second)

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"ok":            true,
		"duration_ms":   3000,
		"shutting_down": shuttingDown.Load(),
	})
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
	body := map[string]interface{}{
		"service":      "graceful-shutdown-go",
		"shutting_down": shuttingDown.Load(),
		"in_flight":    inFlightCount.Load(),
	}

	w.Header().Set("Content-Type", "application/json")
	if shuttingDown.Load() {
		w.WriteHeader(http.StatusServiceUnavailable)
	} else {
		w.WriteHeader(http.StatusOK)
	}
	json.NewEncoder(w).Encode(body)
}

// ==================== main ====================

func main() {
	fmt.Println("========================================")
	fmt.Println("场景 12：优雅关闭 — Go 实现（最优雅！）")
	fmt.Println("信号：kill -TERM <pid> 或 Ctrl+C")
	fmt.Println("========================================")

	mux := http.NewServeMux()
	mux.HandleFunc("/api/long-task", longTaskHandler)
	mux.HandleFunc("/api/health", healthHandler)

	server := &http.Server{
		Addr:    listenAddr,
		Handler: mux,
	}

	// ============ 优雅关闭的核心代码 ============
	// 1. 捕获信号（SIGTERM / SIGINT）
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	// 2. 启动 HTTP 服务（在 goroutine 里）
	go func() {
		log.Printf("[Go] server starting on %s", listenAddr)
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("server error: %v", err)
		}
	}()

	// 3. 等待信号
	<-ctx.Done()
	log.Println("========================================")
	log.Println("[GRACEFUL SHUTDOWN] received signal:", ctx.Err())
	log.Println("[GRACEFUL SHUTDOWN] Step 1/4: 标记 shutting_down=true")
	shuttingDown.Store(true)

	log.Println("[GRACEFUL SHUTDOWN] Step 2/4: 停止接收新请求")
	// Shutdown 会自动关闭监听器

	log.Println("[GRACEFUL SHUTDOWN] Step 3/4: 等待 in-flight 请求完成 (timeout=10s)")
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	if err := server.Shutdown(shutdownCtx); err != nil {
		log.Printf("[GRACEFUL SHUTDOWN] ⚠️ Shutdown 超时！强制关闭: %v", err)
		server.Close() // 强制关闭
	} else {
		log.Println("[GRACEFUL SHUTDOWN] ✅ Shutdown 成功，所有请求完成")
	}

	log.Println("[GRACEFUL SHUTDOWN] Step 4/4: 释放资源 (defer Close() 自动清理)")
	log.Println("[GRACEFUL SHUTDOWN] ✅ Shutdown complete")
	log.Println("========================================")
}
