// 场景 15：结构化并发 + 取消传播 —— Go 用 errgroup.WithContext + context.WithTimeout。
//
// 语义契约（五门语言必须逐字一致，见场景 README）：
//   - 扇出 tasks 个子任务，id = 0..tasks-1，全部并发启动
//   - id == fail_index 的子任务在 fail_after_ms 后"失败"；其余子任务跑满 task_ms 后"完成"
//   - 任一子任务失败 / 父作用域超时 → 取消信号必须传播到所有兄弟任务，兄弟任务提前退出（cancelled）
//   - 作用域退出时所有子任务必须已结束（结构化保证），leaked 恒为 0
//
// Go 的主场优势：context 是一等公民，取消沿调用树自动传播；errgroup 在首个错误时
// 自动 cancel()，Wait() 返回即代表所有 goroutine 已退出 —— 结构化是语言级保证。
package main

import (
	"context"
	"fmt"
	"net/http"
	"sort"
	"sync/atomic"
	"time"

	"github.com/gin-gonic/gin"
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
	"golang.org/x/sync/errgroup"
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

const PORT = 8146

// ---- 运行时统计（供 /stats 暴露，验证器用它做"取消是否真的生效"的延迟判定）----
var (
	activeTasks int64
	statStarted int64
	statDone    int64
	statCancel  int64
	statFailed  int64
)

type fanoutRequest struct {
	Tasks       *int `json:"tasks"`
	TaskMs      *int `json:"task_ms"`
	FailIndex   *int `json:"fail_index"`
	FailAfterMs *int `json:"fail_after_ms"`
	TimeoutMs   *int `json:"timeout_ms"`
}

type fanoutResponse struct {
	Lang        string `json:"lang"`
	Tasks       int    `json:"tasks"`
	TaskMs      int    `json:"task_ms"`
	FailIndex   int    `json:"fail_index"`
	FailAfterMs int    `json:"fail_after_ms"`
	TimeoutMs   int    `json:"timeout_ms"`
	Outcome     string `json:"outcome"` // completed | failed | timeout
	Completed   []int  `json:"completed"`
	Cancelled   []int  `json:"cancelled"`
	Failed      int    `json:"failed"` // -1 表示无任务失败
	ElapsedMs   int64  `json:"elapsed_ms"`
	Leaked      int64  `json:"leaked"` // 作用域退出时仍在运行的子任务数（结构化保证 = 0）
}

type statsResponse struct {
	Lang        string `json:"lang"`
	ActiveTasks int64  `json:"active_tasks"`
	Started     int64  `json:"started"`
	Completed   int64  `json:"completed"`
	Cancelled   int64  `json:"cancelled"`
	Failed      int64  `json:"failed"`
}

func intOr(v *int, def int) int {
	if v == nil {
		return def
	}
	return *v
}

// sleepCancel 等 ms 毫秒；若 ctx 先被取消则返回 false（代表"被取消"）。
// 这是取消传播能生效的关键：等待必须可被中断，不能是无条件 sleep。
func sleepCancel(ctx context.Context, ms int) bool {
	if ms <= 0 {
		select {
		case <-ctx.Done():
			return false
		default:
			return true
		}
	}
	t := time.NewTimer(time.Duration(ms) * time.Millisecond)
	defer t.Stop()
	select {
	case <-t.C:
		return true
	case <-ctx.Done():
		return false
	}
}

func handleFanout(c *gin.Context) {
	var req fanoutRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid json: " + err.Error()})
		return
	}

	tasks := intOr(req.Tasks, 6)
	taskMs := intOr(req.TaskMs, 300)
	failIndex := intOr(req.FailIndex, -1)
	failAfterMs := intOr(req.FailAfterMs, 100)
	timeoutMs := intOr(req.TimeoutMs, 0)

	if tasks < 1 || tasks > 64 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "tasks must be in [1, 64]"})
		return
	}
	if taskMs < 1 || taskMs > 10000 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "task_ms must be in [1, 10000]"})
		return
	}
	if failIndex < -1 || failIndex >= tasks {
		c.JSON(http.StatusBadRequest, gin.H{"error": "fail_index must be in [-1, tasks)"})
		return
	}
	if failAfterMs < 0 || failAfterMs > 10000 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "fail_after_ms must be in [0, 10000]"})
		return
	}
	if timeoutMs < 0 || timeoutMs > 10000 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "timeout_ms must be in [0, 10000]"})
		return
	}

	t0 := time.Now()

	// 父作用域：超时由 context 表达；errgroup 在首个子任务返回 error 时自动 cancel。
	parent := c.Request.Context()
	if timeoutMs > 0 {
		var cancel context.CancelFunc
		parent, cancel = context.WithTimeout(parent, time.Duration(timeoutMs)*time.Millisecond)
		defer cancel()
	}
	g, gctx := errgroup.WithContext(parent)

	outcomes := make([]string, tasks)
	for i := 0; i < tasks; i++ {
		id := i
		g.Go(func() error {
			atomic.AddInt64(&statStarted, 1)
			atomic.AddInt64(&activeTasks, 1)
			defer atomic.AddInt64(&activeTasks, -1)

			if id == failIndex {
				if !sleepCancel(gctx, failAfterMs) {
					outcomes[id] = "cancelled" // 还没来得及失败就被取消（超时抢占）
					return nil
				}
				outcomes[id] = "failed"
				atomic.AddInt64(&statFailed, 1)
				return fmt.Errorf("task %d failed as requested", id)
			}
			if sleepCancel(gctx, taskMs) {
				outcomes[id] = "completed"
				atomic.AddInt64(&statDone, 1)
			} else {
				outcomes[id] = "cancelled"
				atomic.AddInt64(&statCancel, 1)
			}
			return nil
		})
	}

	// Wait 返回 ⇒ 所有 goroutine 都已退出（结构化并发的核心保证）
	_ = g.Wait()
	elapsed := time.Since(t0).Milliseconds()

	completed := make([]int, 0, tasks)
	cancelled := make([]int, 0, tasks)
	failed := -1
	for i, o := range outcomes {
		switch o {
		case "completed":
			completed = append(completed, i)
		case "cancelled":
			cancelled = append(cancelled, i)
		case "failed":
			failed = i
		default:
			outcomes[i] = "cancelled"
			cancelled = append(cancelled, i)
		}
	}
	sort.Ints(completed)
	sort.Ints(cancelled)

	outcome := "completed"
	if failed >= 0 {
		outcome = "failed"
	} else if len(cancelled) > 0 {
		outcome = "timeout"
	}

	logger.Debugw("fanout completed", "outcome", outcome, "elapsedMs", elapsed)

	c.JSON(http.StatusOK, fanoutResponse{
		Lang: "go", Tasks: tasks, TaskMs: taskMs, FailIndex: failIndex,
		FailAfterMs: failAfterMs, TimeoutMs: timeoutMs,
		Outcome: outcome, Completed: completed, Cancelled: cancelled, Failed: failed,
		ElapsedMs: elapsed, Leaked: atomic.LoadInt64(&activeTasks),
	})
}

func handleStats(c *gin.Context) {
	c.JSON(http.StatusOK, statsResponse{
		Lang:        "go",
		ActiveTasks: atomic.LoadInt64(&activeTasks),
		Started:     atomic.LoadInt64(&statStarted),
		Completed:   atomic.LoadInt64(&statDone),
		Cancelled:   atomic.LoadInt64(&statCancel),
		Failed:      atomic.LoadInt64(&statFailed),
	})
}

func handleHealth(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{
		"service": "structured-concurrency",
		"lang":    "go",
		"engine":  "errgroup+context",
	})
}

func main() {
	defer logger.Sync() // flush 日志

	r := gin.Default() // 自带 Recovery + Logger 中间件
	r.GET("/health", handleHealth)
	r.POST("/fanout", handleFanout)
	r.GET("/stats", handleStats)

	addr := fmt.Sprintf("0.0.0.0:%d", PORT)
	logger.Infow("server starting", "addr", addr, "engine", "errgroup+context")
	if err := r.Run(addr); err != nil {
		logger.Fatalw("server failed", "error", err)
	}
}
