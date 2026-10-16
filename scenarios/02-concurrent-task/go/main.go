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
// 用指针类型区分"字段缺省"与"显式传 0"：缺省走默认值 100/100/10，
// 显式传非法值返回 400（与其余四门语言的契约对齐）。
type RunRequest struct {
	TaskCount   *int `json:"task_count"`
	TaskDelayMs *int `json:"task_delay_ms"`
	Concurrency *int `json:"concurrency"`
}

// firstOf 返回指针指向的值，缺省时用默认值
func firstOf(p *int, def int) int {
	if p == nil {
		return def
	}
	return *p
}

// TaskResult 单个任务结果
type TaskResult struct {
	ID         int    `json:"id"`
	Status     string `json:"status"`
	DurationMs int64  `json:"duration_ms"`
}

// RunResponse 响应体
type RunResponse struct {
	TotalTasks  int          `json:"total_tasks"`
	Concurrency int          `json:"concurrency"`
	TotalTimeMs int64        `json:"total_time_ms"`
	Throughput  float64      `json:"throughput"`
	TaskDelayMs int          `json:"task_delay_ms"`
	Results     []TaskResult `json:"results"`
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

	// 字段缺省 → 默认值 100/100/10（与 Python/Java/Rust/TS 一致）
	taskCount := firstOf(req.TaskCount, 100)
	delayMs := firstOf(req.TaskDelayMs, 100)
	concurrency := firstOf(req.Concurrency, 10)

	// 统一契约：显式传入的非法值一律 400，不再静默夹取
	if taskCount < 1 {
		http.Error(w, "task_count must be >= 1", http.StatusBadRequest)
		return
	}
	if delayMs < 0 {
		http.Error(w, "task_delay_ms must be >= 0", http.StatusBadRequest)
		return
	}
	if concurrency < 1 {
		http.Error(w, "concurrency must be >= 1", http.StatusBadRequest)
		return
	}
	// 并发数不超过任务数（契约行为）
	if concurrency > taskCount {
		concurrency = taskCount
	}

	start := time.Now()

	// ========== Go 并发核心 ==========
	// buffered channel 作为 "并发限流阀门"
	// 容量 = concurrency，每个 goroutine 开始前往 channel 发送一个信号，完成后取出
	// channel 满了就阻塞发送 → 天然限制同时执行的 goroutine 数量
	sem := make(chan struct{}, concurrency)
	results := make([]TaskResult, taskCount)
	var wg sync.WaitGroup

	for i := 0; i < taskCount; i++ {
		wg.Add(1)
		sem <- struct{}{} // 占一个槽位（满了就阻塞等待）

		go func(id int) {
			defer wg.Done()
			defer func() { <-sem }() // 释放槽位

			taskStart := time.Now()
			time.Sleep(time.Duration(delayMs) * time.Millisecond)
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
	// 契约：total_time_ms 为 0 时 throughput = task_count（与 Python/Java/Rust/TS 一致；
	// 曾经这里初值 0.0，零延迟任务下五门语言只有 Go 给出 0）
	throughput := float64(taskCount)
	if elapsed > 0 {
		throughput = math.Round(float64(taskCount)*1000.0/float64(elapsed)*100) / 100
	}

	resp := RunResponse{
		TotalTasks:  taskCount,
		Concurrency: concurrency,
		TotalTimeMs: elapsed,
		Throughput:  throughput,
		TaskDelayMs: delayMs,
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
