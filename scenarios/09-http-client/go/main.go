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
	"log"
	"math"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"time"
)

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

// callExternal 带指数退避重试 + 熔断
func callExternal(ctx context.Context, client *http.Client, cb *CircuitBreaker, url string, maxRetries int, timeout time.Duration) (map[string]interface{}, error) {
	resp := map[string]interface{}{
		"url":      url,
		"retries":  0,
		"success":  false,
		"latency":  0,
		"timestamp": time.Now().Format(time.RFC3339),
	}

	// 熔断检查
	if !cb.Allow() {
		resp["error"] = "CIRCUIT_OPEN: 熔断中"
		return resp, fmt.Errorf("熔断中")
	}

	start := time.Now()
	var lastErr error

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

		log.Printf("[HTTP-CLIENT] → GET %s (attempt %d)", url, attempt+1)
		httpResp, err := client.Do(req)
		if err != nil {
			lastErr = err
			if attempt < maxRetries {
				continue // 重试
			}
			continue
		}

		// 5xx 也重试
		if httpResp.StatusCode >= 500 {
			httpResp.Body.Close()
			lastErr = fmt.Errorf("HTTP %d", httpResp.StatusCode)
			if attempt < maxRetries {
				continue
			}
		}

		// 成功
		latency := time.Since(start)
		resp["status_code"] = httpResp.StatusCode
		resp["latency_ms"] = latency.Milliseconds()
		resp["retries"] = attempt
		resp["success"] = httpResp.StatusCode < 400
		cb.RecordSuccess()

		// body 预览
		var body map[string]interface{}
		json.NewDecoder(httpResp.Body).Decode(&body)
		httpResp.Body.Close()
		resp["body_preview"] = body
		return resp, nil
	}

	// 全部重试失败
	cb.RecordFailure()
	resp["status_code"] = 0
	resp["latency_ms"] = time.Since(start).Milliseconds()
	resp["error"] = lastErr.Error()
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
		log.Printf("[Go MockServer] starting on http://localhost%s", mockAddr)
		log.Fatal(http.ListenAndServe(mockAddr, mux))
	}()
}

// ==================== API Handler ====================

var globalCircuitBreaker = NewCircuitBreaker(3, 10*time.Second)

func callExternalHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var req struct {
		URL        string `json:"url"`
		TimeoutMs  int    `json:"timeout_ms"`
		RetryTimes int    `json:"retry_times"`
	}
	json.NewDecoder(r.Body).Decode(&req)
	if req.URL == "" {
		req.URL = fmt.Sprintf("http://localhost%s/ok", mockAddr)
	}
	if req.TimeoutMs == 0 {
		req.TimeoutMs = 5000
	}
	if req.RetryTimes == 0 {
		req.RetryTimes = 2 // 总共最多 3 次（含首次）
	}

	// HTTP Client：Transport 连接池 + 分开配置超时
	transport := &http.Transport{
		MaxIdleConns:        100,
		MaxConnsPerHost:     20,
		IdleConnTimeout:     30 * time.Second,
		DisableKeepAlives:   false,
	}
	client := &http.Client{
		Transport: transport,
		Timeout:   0, // 不用整体 timeout，用 context 分请求控制
	}

	resp, _ := callExternal(context.Background(), client, globalCircuitBreaker,
		req.URL, req.RetryTimes, time.Duration(req.TimeoutMs)*time.Millisecond)

	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	json.NewEncoder(w).Encode(resp)
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"service":     "http-client-go",
		"mock_port":   strings.TrimPrefix(mockAddr, ":"),
		"cb_state":    globalCircuitBreaker.state,
	})
}

// ==================== main ====================

func main() {
	startMockServer()

	mux := http.NewServeMux()
	mux.HandleFunc("/call-external", callExternalHandler)
	mux.HandleFunc("/health", healthHandler)

	// 跑 httptest（占位防止未使用）
	_ = httptest.NewServer

	log.Printf("[Go] http-client server starting on %s", listenAddr)
	if err := http.ListenAndServe(listenAddr, mux); err != nil {
		log.Fatalf("server failed: %v", err)
	}
}
