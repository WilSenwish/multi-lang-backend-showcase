// 场景 14：数据分析处理 —— Go 没有 DataFrame，用 map 手写分组 + gonum 统计函数。
//
// 数据集与其它语言逐位一致：amount = LCG(i+1) 高 32 位 % 100000，category = i % categories。
// 分位数统一 nearest-rank 口径（排序后取 ceil(p*n/100)-1 下标），见场景 README。
package main

import (
	"fmt"
	"net/http"
	"runtime"
	"sort"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
	"gonum.org/v1/gonum/stat"
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
	mult      = uint64(6364136223846793005)
	inc       = uint64(1442695040888963407)
	amountMod = uint64(100_000)
	port      = 8141
)

func amountOf(i uint64) uint64 {
	h := (i+1)*mult + inc // uint64 自然环绕
	return (h >> 32) % amountMod
}

type row struct {
	id   uint64
	cat  int
	amnt uint64
}

type groupStat struct {
	Category string  `json:"category"`
	Count    int     `json:"count"`
	Sum      int64   `json:"sum"`
	Avg      float64 `json:"avg"`
	P50      uint64  `json:"p50"`
	P95      uint64  `json:"p95"`
}

type topRow struct {
	ID       uint64 `json:"id"`
	Category string `json:"category"`
	Amount   uint64 `json:"amount"`
}

type analyzeResponse struct {
	Rows       int         `json:"rows"`
	Categories int         `json:"categories"`
	Groups     []groupStat `json:"groups"`
	Top10      []topRow    `json:"top10"`
	GenMs      int64       `json:"gen_ms"`
	AggMs      int64       `json:"agg_ms"`
	ElapsedMs  int64       `json:"elapsed_ms"`
}

type analyzeRequest struct {
	Rows       *int `json:"rows"`
	Categories *int `json:"categories"`
}

// nearestRank：排序后的 vals 取下标 ceil(p*n/100)-1。
func nearestRank(sorted []uint64, p int) uint64 {
	n := len(sorted)
	idx := (p*n + 99) / 100 // ceil(p*n/100)，p 为整数百分位
	if idx < 1 {
		idx = 1
	}
	if idx > n {
		idx = n
	}
	return sorted[idx-1]
}

func analyze(req analyzeRequest) (analyzeResponse, string) {
	rows, cats := 200_000, 8
	if req.Rows != nil {
		rows = *req.Rows
	}
	if req.Categories != nil {
		cats = *req.Categories
	}
	if rows < 1_000 || rows > 2_000_000 {
		return analyzeResponse{}, "rows must be in [1000, 2000000]"
	}
	if cats < 1 || cats > 64 {
		return analyzeResponse{}, "categories must be in [1, 64]"
	}

	t0 := time.Now()

	// ---- 数据生成 ----
	data := make([]row, rows)
	for i := 0; i < rows; i++ {
		data[i] = row{id: uint64(i), cat: i % cats, amnt: amountOf(uint64(i))}
	}
	t1 := time.Now()

	// ---- 分组聚合：没有 DataFrame，手写 map 分桶 ----
	buckets := make(map[int][]uint64, cats)
	sums := make(map[int]uint64, cats)
	for _, r := range data {
		buckets[r.cat] = append(buckets[r.cat], r.amnt)
		sums[r.cat] += r.amnt
	}

	groups := make([]groupStat, 0, cats)
	for c := 0; c < cats; c++ {
		vals := buckets[c]
		if len(vals) == 0 {
			continue
		}
		sort.Slice(vals, func(a, b int) bool { return vals[a] < vals[b] })
		// gonum 统计函数：均值（本仓库统一口径 avg = sum/count，
		// 这里用 gonum 的 stat.Mean 呈现"生态库 vs 手写"的对比）
		f := make([]float64, len(vals))
		for i, v := range vals {
			f[i] = float64(v)
		}
		groups = append(groups, groupStat{
			Category: fmt.Sprintf("cat-%d", c),
			Count:    len(vals),
			Sum:      int64(sums[c]),
			Avg:      stat.Mean(f, nil), // gonum: 均值
			P50:      nearestRank(vals, 50),
			P95:      nearestRank(vals, 95),
		})
	}

	// ---- Top-10：amount 降序，id 升序 ----
	top := make([]row, len(data))
	copy(top, data)
	sort.Slice(top, func(a, b int) bool {
		if top[a].amnt != top[b].amnt {
			return top[a].amnt > top[b].amnt
		}
		return top[a].id < top[b].id
	})
	top10 := make([]topRow, 0, 10)
	for i := 0; i < 10 && i < len(top); i++ {
		top10 = append(top10, topRow{
			ID:       top[i].id,
			Category: fmt.Sprintf("cat-%d", top[i].cat),
			Amount:   top[i].amnt,
		})
	}
	t2 := time.Now()

	return analyzeResponse{
		Rows:       rows,
		Categories: cats,
		Groups:     groups,
		Top10:      top10,
		GenMs:      t1.Sub(t0).Milliseconds(),
		AggMs:      t2.Sub(t1).Milliseconds(),
		ElapsedMs:  t2.Sub(t0).Milliseconds(),
	}, ""
}

func main() {
	defer logger.Sync() // flush 日志

	r := gin.Default() // 自带 Recovery + Logger 中间件
	r.GET("/health", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{
			"service":    "data-analysis",
			"lang":       "go",
			"engine":     "gonum",
			"gomaxprocs": runtime.GOMAXPROCS(0),
		})
	})
	r.POST("/analyze", func(c *gin.Context) {
		var req analyzeRequest
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "bad json: " + err.Error()})
			return
		}
		resp, errMsg := analyze(req)
		if errMsg != "" {
			c.JSON(http.StatusBadRequest, gin.H{"error": errMsg})
			return
		}
		c.JSON(http.StatusOK, resp)
	})

	addr := ":" + strconv.Itoa(port)
	logger.Infow("server starting", "addr", addr, "engine", "gonum")
	if err := r.Run(addr); err != nil {
		logger.Fatalw("server failed", "error", err)
	}
}
