// Package main 场景 02：并发任务处理 — Go 实现
//
// Go 并发模型特点：
// 1. Goroutine 极轻量（2KB 初始栈），可以随意开
// 2. 但本场景需要公平对比，所以用 buffered channel 限流
// 3. channel 容量 = concurrency，同时最多 concurrency 个 goroutine 在执行
// 4. sync.WaitGroup 等待所有 goroutine 完成
//
// 和 Java ThreadPoolExecutor 的本质区别：
// - Java：线程池内部有队列，超出线程数的任务在队列里等
// - Go：buffered channel 本身就是 "队列"，占满就阻塞发送方
package main

import (
	"encoding/json"
	"log"
	"math"
	"net/http"
	"sync"
	"time"
)

// RunRequest 请求体
type RunRequest struct {
	TaskCount     int `json:"task_count"`
	TaskDelayMs   int `json:"task_delay_ms"`
	Concurrency   int `json:"concurrency"`
}

// TaskResult 单个任务结果
type TaskResult struct {
	ID         int    `json:"id"`
	Status     string `json:"status"`
	DurationMs int64  `json:"duration_ms"`
}

// RunResponse 响应体
type RunResponse struct {
	TotalTasks   int         `json:"total_tasks"`
	Concurrency  int         `json:"concurrency"`
	TotalTimeMs  int64       `json:"total_time_ms"`
	Throughput   float64     `json:"throughput"`
	TaskDelayMs  int         `json:"task_delay_ms"`
	Results      []TaskResult `json:"results"`
}

const listenAddr = ":8086"

func runHandler(w http.ResponseWriter, r *http.Request) {
	// 只接受 POST
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	// 解析请求
	var req RunRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "invalid json: "+err.Error(), http.StatusBadRequest)
		return
	}

	// 边界保护
	if req.TaskCount < 1 {
		req.TaskCount = 100
	}
	if req.TaskDelayMs < 0 {
		req.TaskDelayMs = 0
	}
	if req.Concurrency < 1 {
		req.Concurrency = 10
	}
	if req.Concurrency > req.TaskCount {
		req.Concurrency = req.TaskCount
	}

	start := time.Now()

	// ========== Go 并发核心 ==========
	// buffered channel 作为 "并发限流阀门"
	// 容量 = concurrency，每个 goroutine 开始前往 channel 发送一个信号，完成后取出
	// channel 满了就阻塞发送 → 天然限制同时执行的 goroutine 数量
	sem := make(chan struct{}, req.Concurrency)
	results := make([]TaskResult, req.TaskCount)
	var wg sync.WaitGroup

	for i := 0; i < req.TaskCount; i++ {
		wg.Add(1)
		sem <- struct{}{} // 占一个槽位（满了就阻塞等待）

		go func(id int) {
			defer wg.Done()
			defer func() { <-sem }() // 释放槽位

			taskStart := time.Now()
			time.Sleep(time.Duration(req.TaskDelayMs) * time.Millisecond)
			duration := time.Since(taskStart).Milliseconds()

			results[id] = TaskResult{
				ID:         id,
				Status:     "ok",
				DurationMs: duration,
			}
		}(i)
	}

	wg.Wait()
	// ==============================

	elapsed := time.Since(start).Milliseconds()
	throughput := 0.0
	if elapsed > 0 {
		throughput = math.Round(float64(req.TaskCount)*1000.0/float64(elapsed)*100) / 100
	}

	resp := RunResponse{
		TotalTasks:  req.TaskCount,
		Concurrency: req.Concurrency,
		TotalTimeMs: elapsed,
		Throughput:  throughput,
		TaskDelayMs: req.TaskDelayMs,
		Results:     results,
	}

	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	if err := json.NewEncoder(w).Encode(resp); err != nil {
		log.Printf("encode response error: %v", err)
	}
}

func main() {
	mux := http.NewServeMux()
	mux.HandleFunc("/run", runHandler)

	log.Printf("[Go] concurrent-task server starting on %s", listenAddr)
	if err := http.ListenAndServe(listenAddr, mux); err != nil {
		log.Fatalf("server failed: %v", err)
	}
}
