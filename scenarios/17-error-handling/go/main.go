/**
 * 场景 17：错误处理深水区 —— Go 版本。
 *
 * 语义契约（五门语言必须逐字一致，见场景 README）：
 *   GET /errors/{kind} —— 五种"错误形态"，每一种都必须落成同一个结构化响应体：
 *     - not_found      → 404 NOT_FOUND          cause_chain = ["user 42 not found"]
 *     - validation     → 400 VALIDATION_FAILED  details = ["email: required", "age: must be >= 0"]
 *     - wrap_chain     → 500 WRAPPED            cause_chain 四层，最外层 → 根因
 *     - panic          → 500 INTERNAL           未捕获异常被兜底，recovered=true，进程必须存活
 *     - async_detached → 202 ACCEPTED           错误发生在脱离请求上下文的 goroutine 里
 *   GET /stats → handled / unhandled / panics_recovered / last_unhandled / last_trace_id
 *   请求头 X-Trace-Id 必须原样回显：trace_id 有没有穿过错误路径，是"深水区"的第一课。
 *
 * Go 的取舍：
 *   - error 是**值**：不带调用栈、不带 code，链式上下文全靠 fmt.Errorf 的 %w 手工包装。
 *     写成 %v 链就断了，而编译器不会提醒 —— 这是 Go 错误处理最常见的事故。
 *   - panic 只在**当前 goroutine** 展开：http.Server 自己也会 recover，但那样客户端
 *     拿到的是一条被断开的连接（EOF）而不是 500；要给出结构化错误必须在中间件里自己接住。
 *   - goroutine 里的错误没有任何运行时钩子：漏掉"把 err 交给谁"这一步就是彻底静默；
 *     更糟的是 goroutine 里的 panic 会**直接终止整个进程**（HTTP handler 有 recover 兜着，
 *     自己起的 goroutine 没有）。
 */

package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/http"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

const PORT = 8156

// ---------------------------------------------------------------- 错误类型

// Go 里"带 code / 带 cause / 带 details"的错误只能自己定义结构体。
// 标准库没有这个概念，%w 只负责把 cause 串起来，其余信息全靠自定义类型承载。
type appError struct {
	Code    string
	Msg     string
	Cause   error
	Details []string
}

func (e *appError) Error() string { return e.Msg }
func (e *appError) Unwrap() error { return e.Cause }

// ---------------------------------------------------------------- 响应体

type errorBody struct {
	Kind         string   `json:"kind"`
	Code         string   `json:"code"`
	Message      string   `json:"message"`
	TraceID      string   `json:"trace_id"`
	CauseChain   []string `json:"cause_chain"`
	Details      []string `json:"details"`
	StackPresent bool     `json:"stack_present"`
	Recovered    bool     `json:"recovered"`
}

type statsBody struct {
	Handled         int    `json:"handled"`
	Unhandled       int    `json:"unhandled"`
	PanicsRecovered int    `json:"panics_recovered"`
	LastUnhandled   string `json:"last_unhandled"`
	LastTraceID     string `json:"last_trace_id"`
}

// ---------------------------------------------------------------- 计数器

type counters struct {
	mu            sync.Mutex
	handled       int
	unhandled     int
	panics        int
	lastUnhandled string
	lastTraceID   string
}

var st counters
var tidSeq int64

func (c *counters) noteTrace(id string) {
	c.mu.Lock()
	c.lastTraceID = id
	c.mu.Unlock()
}

func (c *counters) noteHandled() {
	c.mu.Lock()
	c.handled++
	c.mu.Unlock()
}

func (c *counters) notePanic() {
	c.mu.Lock()
	c.handled++
	c.panics++
	c.mu.Unlock()
}

func (c *counters) noteUnhandled(msg string) {
	c.mu.Lock()
	c.unhandled++
	c.lastUnhandled = msg
	c.mu.Unlock()
}

func (c *counters) snapshot() statsBody {
	c.mu.Lock()
	defer c.mu.Unlock()
	return statsBody{
		Handled:         c.handled,
		Unhandled:       c.unhandled,
		PanicsRecovered: c.panics,
		LastUnhandled:   c.lastUnhandled,
		LastTraceID:     c.lastTraceID,
	}
}

// ---------------------------------------------------------------- 工具

// causeChain 沿 Unwrap() 一路收集 Error()：最外层 → 根因。
// 这是每个 Go 项目都要抄一遍的样板：标准库没有"遍历错误链"的现成工具。
func causeChain(err error) []string {
	out := make([]string, 0, 4)
	for e := err; e != nil; e = errors.Unwrap(e) {
		out = append(out, e.Error())
		if len(out) >= 32 {
			break
		}
	}
	return out
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

// detachedWork 模拟"脱离请求上下文的异步工作"：它返回一个普通的 error。
// 关键点是调用方——没人接收这个返回值时，它就彻底消失了。
func detachedWork() error {
	time.Sleep(120 * time.Millisecond)
	return errors.New("async-boom-17")
}

// ---------------------------------------------------------------- 处理函数

func errorHandler(w http.ResponseWriter, r *http.Request) {
	kind := strings.TrimPrefix(r.URL.Path, "/errors/")
	traceID := r.Header.Get("X-Trace-Id")
	if traceID == "" {
		traceID = fmt.Sprintf("tid-%d", atomic.AddInt64(&tidSeq, 1))
	}
	st.noteTrace(traceID)

	switch kind {

	case "not_found":
		st.noteHandled()
		err := &appError{Code: "NOT_FOUND", Msg: "user 42 not found"}
		writeJSON(w, http.StatusNotFound, errorBody{
			Kind: "not_found", Code: err.Code, Message: err.Msg, TraceID: traceID,
			CauseChain: causeChain(err), Details: []string{},
			StackPresent: false, Recovered: false,
		})

	case "validation":
		st.noteHandled()
		err := &appError{
			Code:    "VALIDATION_FAILED",
			Msg:     "invalid request",
			Details: []string{"email: required", "age: must be >= 0"},
		}
		writeJSON(w, http.StatusBadRequest, errorBody{
			Kind: "validation", Code: err.Code, Message: err.Msg, TraceID: traceID,
			CauseChain: causeChain(err), Details: err.Details,
			StackPresent: false, Recovered: false,
		})

	case "wrap_chain":
		st.noteHandled()
		// 四层包装：db → repository → service → handler。
		// 每一层都用 %w 把 cause 挂上去；任意一层写成 %v，链就断在那里。
		root := &appError{Code: "DB", Msg: "db: row 42 not found"}
		repo := &appError{Code: "REPO", Msg: "repository: load user", Cause: root}
		svc := &appError{Code: "SERVICE", Msg: "service: get profile", Cause: repo}
		top := &appError{Code: "HANDLER", Msg: "handler: GET /errors/wrap_chain", Cause: svc}
		writeJSON(w, http.StatusInternalServerError, errorBody{
			Kind: "wrap_chain", Code: "WRAPPED", Message: top.Msg, TraceID: traceID,
			CauseChain: causeChain(top), Details: []string{},
			StackPresent: false, Recovered: false,
		})

	case "panic":
		// 未捕获异常：交给 recoverMiddleware 兜底（计数也在那里做）。
		panic("boom-17")

	case "async_detached":
		// ⭐ 深水区：goroutine 里的错误没有任何运行时钩子。
		// 下面这 3 行（recover + if err != nil + noteUnhandled）全是手写的，
		// 少任何一行，这个错误都不会出现在任何日志或指标里。
		go func() {
			defer func() {
				if rec := recover(); rec != nil {
					st.noteUnhandled(fmt.Sprintf("%v", rec))
				}
			}()
			if err := detachedWork(); err != nil {
				st.noteUnhandled(err.Error())
			}
		}()
		writeJSON(w, http.StatusAccepted, errorBody{
			Kind: "async_detached", Code: "ACCEPTED", Message: "async work spawned",
			TraceID: traceID, CauseChain: []string{}, Details: []string{},
			StackPresent: false, Recovered: false,
		})

	default:
		msg := "unknown kind: " + kind
		writeJSON(w, http.StatusNotFound, errorBody{
			Kind: kind, Code: "UNKNOWN_KIND", Message: msg, TraceID: traceID,
			CauseChain: []string{msg}, Details: []string{},
			StackPresent: false, Recovered: false,
		})
	}
}

// recoverMiddleware 是 Go 这边"从 panic 中恢复并给出结构化错误"的唯一位置。
// 不写它，net/http 只会把这条连接断掉（客户端看到 EOF），服务端日志里也没有这条错误。
func recoverMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		defer func() {
			rec := recover()
			if rec == nil {
				return
			}
			// recover 拿到的是一个 any：没有类型、没有栈、没有 cause。
			// 想要栈只能在这里调 debug.Stack() 现抓（开销不小，生产里通常只进日志）。
			// 这里刻意不抓 —— 就是要让 stack_present=false 暴露"Go 的 panic 默认不带栈"。
			traceID := r.Header.Get("X-Trace-Id")
			if traceID == "" {
				traceID = "tid-unknown"
			}
			st.notePanic()
			msg := fmt.Sprintf("%v", rec)
			writeJSON(w, http.StatusInternalServerError, errorBody{
				Kind: "panic", Code: "INTERNAL", Message: msg, TraceID: traceID,
				CauseChain: []string{msg}, Details: []string{},
				StackPresent: false, Recovered: true,
			})
		}()
		next.ServeHTTP(w, r)
	})
}

// ---------------------------------------------------------------- main

func main() {
	mux := http.NewServeMux()
	mux.HandleFunc("/stats", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, st.snapshot())
	})
	mux.Handle("GET /errors/", recoverMiddleware(http.HandlerFunc(errorHandler)))

	addr := fmt.Sprintf(":%d", PORT)
	log.Printf("[go] 17-error-handling listening on %s", addr)
	if err := http.ListenAndServe(addr, mux); err != nil {
		log.Fatal(err)
	}
}
