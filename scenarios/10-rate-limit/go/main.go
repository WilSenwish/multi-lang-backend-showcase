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
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"sync/atomic"

	"golang.org/x/time/rate"
)

const listenAddr = ":8121"

// ============ 全局限流器 ============

var (
	limiter         = rate.NewLimiter(1.0, 10) // QPS=1, burst=10
	totalRequests   int64
	allowedRequests int64
	rejectedRequests int64
)

// ============ Handler ============

func write429(w http.ResponseWriter, retryAfterMs int64) {
	w.Header().Set("Content-Type", "application/json")
	retryAfterSec := retryAfterMs / 1000
	if retryAfterSec < 1 {
		retryAfterSec = 1
	}
	w.Header().Set("Retry-After", fmt.Sprintf("%d", retryAfterSec))
	w.WriteHeader(http.StatusTooManyRequests)

	resp := map[string]interface{}{
		"error":          "rate limit exceeded",
		"retry_after_ms": retryAfterMs,
		"total":          atomic.LoadInt64(&totalRequests),
		"allowed":        atomic.LoadInt64(&allowedRequests),
		"rejected":       atomic.LoadInt64(&rejectedRequests),
	}
	json.NewEncoder(w).Encode(resp)

	log.Printf("[RateLimit] 429 被限流: retryAfter=%dms", retryAfterMs)
}

func heavyHandler(w http.ResponseWriter, r *http.Request) {
	atomic.AddInt64(&totalRequests, 1)

	// Reserve 一次：拿到令牌则 delay=0 放行；拿不到则立刻 Cancel 退还（不能白占一个未来令牌，
	// 否则每拒绝一次都把"下一次可用时间"往后推，Retry-After 会从 1s 一路涨到 15s+）。
	reservation := limiter.Reserve()
	if !reservation.OK() {
		atomic.AddInt64(&rejectedRequests, 1)
		write429(w, 1000)
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
		write429(w, retryAfterMs)
		return
	}

	atomic.AddInt64(&allowedRequests, 1)
	log.Printf("[RateLimit] 200 通过")

	w.Header().Set("Content-Type", "application/json")
	resp := map[string]interface{}{
		"ok":       true,
		"endpoint": "/api/heavy",
		"total":    atomic.LoadInt64(&totalRequests),
		"allowed":  atomic.LoadInt64(&allowedRequests),
		"rejected": atomic.LoadInt64(&rejectedRequests),
	}
	json.NewEncoder(w).Encode(resp)
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
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
	fmt.Println("限流配置：QPS=1, burst=10 (每秒 1 个令牌，桶容量 10)")
	fmt.Println("快速连续请求 /api/heavy，超过 10 个后会 429")

	mux := http.NewServeMux()
	mux.HandleFunc("/api/heavy", heavyHandler)
	mux.HandleFunc("/health", healthHandler)

	log.Printf("[Go] rate-limit server starting on %s", listenAddr)
	if err := http.ListenAndServe(listenAddr, mux); err != nil {
		log.Fatalf("server failed: %v", err)
	}
}
