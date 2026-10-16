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
	"encoding/json"
	"fmt"
	"log"
	"math"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"sync"
	"unicode"
)

const listenAddr = ":8101"

// ==================== 数据结构 ====================

type Chunk struct {
	ID      string
	Text    string
	Source  string
	Vector  []float64 // 词频向量
}

type Store struct {
	mu    sync.RWMutex
	chunks map[string]*Chunk
	vocab []string // 全局词表（索引 = 向量维度）
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

	// 按空行切段落
	parts := regexp.MustCompile(`\n\s*\n`).Split(content, -1)
	count := 0
	for i, p := range parts {
		trimmed := strings.TrimSpace(p)
		if len(trimmed) < 10 {
			continue
		}
		id := fmt.Sprintf("%s#%d", fileName, i)
		s.chunks[id] = &Chunk{ID: id, Text: trimmed, Source: fileName}
		count++
	}

	// 重建词表 + 向量
	s.rebuildVectors()
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

	if len(s.vocab) == 0 {
		return nil
	}

	qVec := buildVector(question, s.vocab)

	var results []SourceResult
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

	// 按 score 降序
	sort.Slice(results, func(i, j int) bool {
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
	fields := regexp.MustCompile(`[^a-z0-9\u4e00-\u9fff]+`).Split(text, -1)
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
	Question string `json:"question"`
	TopK     int    `json:"top_k"`
}

func writeJSON(w http.ResponseWriter, v interface{}) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	json.NewEncoder(w).Encode(v)
}

func ingestHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var req IngestReq
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, map[string]interface{}{"success": false, "error": "invalid json"})
		return
	}

	chunks, err := store.IngestFile(req.FilePath)
	if err != nil {
		writeJSON(w, map[string]interface{}{"success": false, "error": err.Error()})
		return
	}

	writeJSON(w, map[string]interface{}{
		"success":             true,
		"file":                req.FilePath,
		"chunks":              chunks,
		"embeddings_generated": chunks,
		"vocab_size":          len(store.vocab),
	})
}

func askHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var req AskReq
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, map[string]interface{}{"success": false, "error": "invalid json"})
		return
	}
	if req.TopK == 0 {
		req.TopK = 3
	}

	sources := store.Search(req.Question, req.TopK)
	answer := mockAnswer(req.Question, sources)

	writeJSON(w, map[string]interface{}{
		"success":  true,
		"question": req.Question,
		"answer":   answer,
		"sources":  sources,
		"mode":     "local-mock",
	})
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
	store.mu.RLock()
	defer store.mu.RUnlock()
	writeJSON(w, map[string]interface{}{
		"service":      "simple-rag-go",
		"chunks_loaded": len(store.chunks),
		"vocab_size":   len(store.vocab),
	})
}

// ==================== main ====================

// 防止 unicode 包未使用（占位）
var _ = unicode.IsLetter

func main() {
	mux := http.NewServeMux()
	mux.HandleFunc("/ingest", ingestHandler)
	mux.HandleFunc("/ask", askHandler)
	mux.HandleFunc("/health", healthHandler)

	log.Printf("[Go] simple-rag server starting on %s", listenAddr)
	if err := http.ListenAndServe(listenAddr, mux); err != nil {
		log.Fatalf("server failed: %v", err)
	}
}
