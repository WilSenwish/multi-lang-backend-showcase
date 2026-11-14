// Package main 场景 06：轻量 RAG Demo — Go 实现
//
// Go 版本特点：
// 1. 全部标准库实现，零外部依赖
// 2. 向量存储用 map + mutex 保证并发安全
// 3. 词频向量 + cosine similarity 检索
// 4. 和 Java 实现完全相同的 pipeline
//
// Go 在向量计算上的优势：编译型语言，无 GC 开销，纯 CPU 计算很快
package main

import (
	"fmt"
	"math"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"sync"
	"unicode"
	"unicode/utf8"

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

const listenAddr = ":8101"

// ==================== 数据结构 ====================

type Chunk struct {
	ID     string
	Text   string
	Source string
	Vector []float64 // 词频向量
}

type Store struct {
	mu     sync.RWMutex
	chunks map[string]*Chunk
	vocab  []string // 全局词表（索引 = 向量维度）
}

func NewStore() *Store {
	return &Store{
		chunks: make(map[string]*Chunk),
	}
}

// ==================== 摄入 ====================

func (s *Store) IngestFile(filePath string) (int, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	data, err := os.ReadFile(filePath)
	if err != nil {
		return 0, fmt.Errorf("读取文件失败: %w", err)
	}

	content := string(data)
	fileName := filepath.Base(filePath)

	// 每次摄入重建 store（与 Java/Python/Rust/TS 一致：最后一次摄入的文档生效）
	s.chunks = make(map[string]*Chunk)

	// 按空行切段落
	parts := regexp.MustCompile(`\n\s*\n`).Split(content, -1)
	count := 0
	for i, p := range parts {
		trimmed := strings.TrimSpace(p)
		// 用字符数而非字节数判断"太短"（与 Python/Rust/TS 一致；
		// 字节数会把 5 个汉字=15 字节误判为"够长"）
		if utf8.RuneCountInString(trimmed) < 10 {
			continue
		}
		id := fmt.Sprintf("%s#%d", fileName, i)
		s.chunks[id] = &Chunk{ID: id, Text: trimmed, Source: fileName}
		count++
	}

	// 重建词表 + 向量
	s.rebuildVectors()
	logger.Infow("ingest file", "file", fileName, "chunks", count, "vocab", len(s.vocab))
	return count, nil
}

func (s *Store) rebuildVectors() {
	// 收集所有词
	vocabSet := make(map[string]struct{})
	for _, c := range s.chunks {
		for _, w := range tokenize(c.Text) {
			vocabSet[w] = struct{}{}
		}
	}

	// 固定顺序的词表（按字母排序保证可预测）
	s.vocab = make([]string, 0, len(vocabSet))
	for w := range vocabSet {
		s.vocab = append(s.vocab, w)
	}
	sort.Strings(s.vocab)

	// 给每个 chunk 生成向量
	for _, c := range s.chunks {
		c.Vector = buildVector(c.Text, s.vocab)
	}
}

// ==================== 检索 ====================

type SourceResult struct {
	Text   string  `json:"text"`
	Source string  `json:"source"`
	Score  float64 `json:"score"`
}

func (s *Store) Search(question string, topK int) []SourceResult {
	s.mu.RLock()
	defer s.mu.RUnlock()

	// 空结果也要返回 [] 而不是 nil：nil 会被 json 编码成 null，与其余四门的 [] 不一致
	empty := []SourceResult{}
	if len(s.vocab) == 0 {
		return empty
	}

	qVec := buildVector(question, s.vocab)

	results := empty
	for _, c := range s.chunks {
		score := cosineSimilarity(qVec, c.Vector)
		if score > 0 {
			results = append(results, SourceResult{
				Text:   c.Text,
				Source: c.Source,
				Score:  roundScore(score),
			})
		}
	}

	// 按 score 降序（SliceStable：同分保持遍历顺序，避免 sort.Slice 的不稳定排序带来不确定性）
	sort.SliceStable(results, func(i, j int) bool {
		return results[i].Score > results[j].Score
	})

	if len(results) > topK {
		results = results[:topK]
	}
	return results
}

func mockAnswer(question string, sources []SourceResult) string {
	if len(sources) == 0 {
		return "我没有找到相关信息，请先 POST /ingest 摄入文档。"
	}
	var sb strings.Builder
	fmt.Fprintf(&sb, "根据摄入的文档，关于「%s」的相关内容：\n\n", question)
	for i, s := range sources {
		fmt.Fprintf(&sb, "%d. (来自 %s, 相关度 %.4f) %s\n", i+1, s.Source, s.Score, s.Text)
	}
	return sb.String()
}

// ==================== 辅助 ====================

// tokenize 分词：小写化 + 提取中英文词
func tokenize(text string) []string {
	text = strings.ToLower(text)
	var tokens []string
	// 按非单词字符分割
	fields := regexp.MustCompile(`[^a-z0-9\x{4e00}-\x{9fff}]+`).Split(text, -1)
	for _, f := range fields {
		f = strings.TrimSpace(f)
		// 过滤太短
		if len([]rune(f)) >= 2 {
			tokens = append(tokens, f)
		}
	}
	return tokens
}

// buildVector 词频向量
func buildVector(text string, vocab []string) []float64 {
	tokens := tokenize(text)
	// 词频 map
	freq := make(map[string]int)
	for _, t := range tokens {
		freq[t]++
	}
	vec := make([]float64, len(vocab))
	for i, w := range vocab {
		vec[i] = float64(freq[w])
	}
	return vec
}

// cosineSimilarity 余弦相似度
func cosineSimilarity(a, b []float64) float64 {
	var dot, normA, normB float64
	for i := range a {
		dot += a[i] * b[i]
		normA += a[i] * a[i]
		normB += b[i] * b[i]
	}
	if normA == 0 || normB == 0 {
		return 0
	}
	return dot / (math.Sqrt(normA) * math.Sqrt(normB))
}

func roundScore(v float64) float64 {
	return math.Round(v*10000) / 10000
}

// ==================== HTTP Handler ====================

var store = NewStore()

type IngestReq struct {
	FilePath string `json:"file_path"`
}

type AskReq struct {
	// 指针字段：区分"缺省"与"显式传值"。非指针 int 缺省即 0，与显式 0 无法区分
	// （显式 top_k=0 应走 400 校验，缺省才用默认值 3）。
	Question *string `json:"question"`
	TopK     *int    `json:"top_k"`
}

func ingestHandler(c *gin.Context) {
	var req IngestReq
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(400, gin.H{"error": "invalid json"})
		return
	}

	chunks, err := store.IngestFile(req.FilePath)
	if err != nil {
		// 文件不存在/是目录/权限问题都是客户端给的 path 不对 → 400（与 Python/Rust/TS 一致）
		c.JSON(400, gin.H{"error": err.Error()})
		return
	}

	c.JSON(200, gin.H{
		"success":              true,
		"file":                 req.FilePath,
		"chunks":               chunks,
		"embeddings_generated": chunks,
		"vocab_size":           len(store.vocab),
	})
}

func askHandler(c *gin.Context) {
	var req AskReq
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(400, gin.H{"error": "invalid json"})
		return
	}
	// question 缺失/类型错 → 400；空串是合法输入（检索不到内容，返回兜底答案）
	if req.Question == nil {
		c.JSON(400, gin.H{"error": "缺少 question"})
		return
	}
	topK := 3
	if req.TopK != nil {
		topK = *req.TopK
	}
	if topK < 1 {
		c.JSON(400, gin.H{"error": "top_k 必须 >= 1"})
		return
	}

	sources := store.Search(*req.Question, topK)
	answer := mockAnswer(*req.Question, sources)

	c.JSON(200, gin.H{
		"success":  true,
		"question": *req.Question,
		"answer":   answer,
		"sources":  sources,
		"mode":     "local-mock",
	})
}

func healthHandler(c *gin.Context) {
	store.mu.RLock()
	defer store.mu.RUnlock()
	c.JSON(200, gin.H{
		"service":       "simple-rag-go",
		"chunks_loaded": len(store.chunks),
		"vocab_size":    len(store.vocab),
	})
}

// ==================== main ====================

// 防止 unicode 包未使用（占位）
var _ = unicode.IsLetter

func main() {
	defer logger.Sync() // flush 日志

	r := gin.Default() // 自带 Recovery + Logger 中间件
	r.POST("/ingest", ingestHandler)
	r.POST("/ask", askHandler)
	r.GET("/health", healthHandler)

	logger.Infow("server starting", "addr", listenAddr)
	if err := r.Run(listenAddr); err != nil {
		logger.Fatalw("server failed", "error", err)
	}
}
