// Package main 场景 13：CPU 密集并行计算 — Go 实现（纯标准库）
//
// 统一 API 契约：
//
//	POST /compute
//	{"task_count":8,"iterations":2000000,"concurrency":4}
//	→ {"total_tasks":8,"iterations":2000000,"concurrency":4,"cpu_cores":10,
//	   "total_time_ms":1234,"checksum":"<uint64 无符号十进制>",
//	   "results":[{"id":0,"checksum":"<uint64>","duration_ms":150}, ...]}
//
// Go 的并发模型在本场景的优势：
//  1. goroutine 调度由 runtime 接管（M:N），CPU 密集下 GOMAXPROCS 会自动铺满所有 P；
//  2. 限制并发数量只需要一个带缓冲 channel —— 语法上就是"信号量"，无需线程池抽象；
//  3. uint64 原生环绕，与 Rust u64 语义一致，不需要任何特殊处理。
//
// 与 Python / TS 的对照点：
//   - Python 的多线程受 GIL 限制，CPU 密集必须换成 multiprocessing；
//   - Node 是单线程，必须自己搭 worker_threads 池。
//   Go 用「一个 channel + go 关键字」就能做到的事，这两门语言要动用进程/线程池。
package main

import (
	"fmt"
	"runtime"
	"strconv"
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
	listenAddr = ":8136"

	// MMIX 线性同余发生器常数：state = state * mult + inc (mod 2^64)
	mult = uint64(6364136223846793005)
	inc  = uint64(1442695040888963407)

	defaultTaskCount   = 8
	defaultIterations  = uint64(2000000)
	defaultConcurrency = 4
)

// ComputeRequest 计算请求；用指针区分"未传"与"传了 0"，便于填缺省值
type ComputeRequest struct {
	TaskCount   *int    `json:"task_count"`
	Iterations  *uint64 `json:"iterations"`
	Concurrency *int    `json:"concurrency"`
}

// TaskResult 单任务结果
type TaskResult struct {
	ID         int    `json:"id"`
	Checksum   string `json:"checksum"`
	DurationMs int64  `json:"duration_ms"`
}

// ComputeResponse 计算响应
type ComputeResponse struct {
	TotalTasks  int          `json:"total_tasks"`
	Iterations  uint64       `json:"iterations"`
	Concurrency int          `json:"concurrency"`
	CPUCores    int          `json:"cpu_cores"`
	TotalTimeMs int64        `json:"total_time_ms"`
	Checksum    string       `json:"checksum"`
	Results     []TaskResult `json:"results"`
}

// computeState 跑 iterations 次 LCG 迭代，返回 uint64 环绕结果
func computeState(id int, iterations uint64) uint64 {
	state := uint64(id) + 1
	for i := uint64(0); i < iterations; i++ {
		state = state*mult + inc
	}
	return state
}

func handleCompute(c *gin.Context) {
	var req ComputeRequest
	// 允许空 body：EOF 时按缺省值处理
	_ = c.ShouldBindJSON(&req)

	taskCount := defaultTaskCount
	if req.TaskCount != nil && *req.TaskCount >= 1 {
		taskCount = *req.TaskCount
	}
	iterations := defaultIterations
	if req.Iterations != nil && *req.Iterations >= 1 {
		iterations = *req.Iterations
	}
	concurrency := defaultConcurrency
	if req.Concurrency != nil && *req.Concurrency >= 1 {
		concurrency = *req.Concurrency
	}
	if concurrency > taskCount {
		concurrency = taskCount
	}

	start := time.Now()

	// 带缓冲 channel 就是信号量：容量 = 并发上限
	sem := make(chan struct{}, concurrency)
	var wg sync.WaitGroup

	results := make([]TaskResult, taskCount)
	states := make([]uint64, taskCount)

	for i := 0; i < taskCount; i++ {
		wg.Add(1)
		go func(id int) {
			defer wg.Done()
			sem <- struct{}{}        // 占用一个名额（满了就阻塞）
			defer func() { <-sem }() // 释放名额

			t0 := time.Now()
			state := computeState(id, iterations)
			states[id] = state
			// 每个 goroutine 只写自己的下标，不存在数据竞争
			results[id] = TaskResult{
				ID:         id,
				Checksum:   strconv.FormatUint(state, 10),
				DurationMs: time.Since(t0).Milliseconds(),
			}
		}(i)
	}
	wg.Wait()

	// 累加和取 uint64 环绕（加法模 2^64 满足交换律，与执行顺序无关）
	var sum uint64
	for _, s := range states {
		sum += s
	}

	resp := ComputeResponse{
		TotalTasks:  taskCount,
		Iterations:  iterations,
		Concurrency: concurrency,
		CPUCores:    runtime.NumCPU(),
		TotalTimeMs: time.Since(start).Milliseconds(),
		Checksum:    strconv.FormatUint(sum, 10),
		Results:     results,
	}

	c.JSON(200, resp)
}

func main() {
	defer logger.Sync() // flush 日志

	r := gin.Default() // 自带 Recovery + Logger 中间件
	r.POST("/compute", handleCompute)
	r.GET("/health", func(c *gin.Context) {
		c.JSON(200, gin.H{
			"service":    "cpu-bound-parallel-go",
			"cpu_cores":  runtime.NumCPU(),
			"gomaxprocs": runtime.GOMAXPROCS(0),
		})
	})

	logger.Infow("server starting", "addr", listenAddr, "GOMAXPROCS", runtime.GOMAXPROCS(0))
	if err := r.Run(listenAddr); err != nil {
		logger.Fatalw("server failed", "error", err)
	}
}
