package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"
)

// 场景 04：文件读写 & 目录遍历 — Go 实现
//
// Go 文件 IO 特点：
// 1. os 包同步 API，零依赖
// 2. filepath 处理路径（跨平台）
// 3. os.MkdirAll 递归创建目录
// 4. filepath.WalkDir 递归遍历（Go 1.16+）
// 5. os.WriteFile / os.ReadFile 非常方便
//
// 和 Java NIO.2 对比：
// - Go 更简洁，但功能没 Java 全（Java 有 WatchService、AttributeViews 等）
// - Go 写并发文件 IO 要配合 goroutine，Java Spring Boot 线程池自动处理

const listenAddr = ":8096"

// ==================== 请求/响应结构 ====================

type WriteRequest struct {
	Path    string      `json:"path"`
	Content interface{} `json:"content"`
	Append  bool        `json:"append"`
}

// ==================== 3 个 Handler ====================

// POST /file/write
func writeHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var req WriteRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "invalid json: "+err.Error(), http.StatusBadRequest)
		return
	}

	resp := map[string]interface{}{}

	// 把 content 转成字符串写入
	content := contentToString(req.Content)
	// 确保父目录存在
	if dir := filepath.Dir(req.Path); dir != "." && dir != "/" {
		os.MkdirAll(dir, 0755)
	}

	var err error
	if req.Append {
		f, e := os.OpenFile(req.Path, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
		if e != nil {
			err = e
		} else {
			_, err = f.WriteString(content)
			f.Close()
		}
	} else {
		err = os.WriteFile(req.Path, []byte(content), 0644)
	}

	if err != nil {
		resp["success"] = false
		resp["error"] = err.Error()
	} else {
		resp["success"] = true
		resp["path"] = req.Path
		resp["bytes_written"] = len(content)
		resp["append"] = req.Append
	}

	writeJSON(w, resp)
}

// GET /file/read
func readHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	path := r.URL.Query().Get("path")
	if path == "" {
		http.Error(w, "missing path param", http.StatusBadRequest)
		return
	}

	info, err := os.Stat(path)
	if err != nil {
		if os.IsNotExist(err) {
			http.Error(w, "文件不存在: "+path, http.StatusNotFound)
		} else {
			http.Error(w, err.Error(), http.StatusInternalServerError)
		}
		return
	}
	if info.IsDir() {
		http.Error(w, "不是文件: "+path, http.StatusBadRequest)
		return
	}

	data, err := os.ReadFile(path)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	writeJSON(w, map[string]interface{}{
		"path":    path,
		"content": string(data),
		"bytes":   len(data),
	})
}

// GET /file/scan
func scanHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	dir := r.URL.Query().Get("dir")
	if dir == "" {
		http.Error(w, "missing dir param", http.StatusBadRequest)
		return
	}
	recursive := r.URL.Query().Get("recursive") != "false" // 默认 true

	info, err := os.Stat(dir)
	if err != nil {
		if os.IsNotExist(err) {
			http.Error(w, "目录不存在: "+dir, http.StatusNotFound)
		} else {
			http.Error(w, err.Error(), http.StatusInternalServerError)
		}
		return
	}
	if !info.IsDir() {
		http.Error(w, "不是目录: "+dir, http.StatusBadRequest)
		return
	}

	fileCount := 0
	totalBytes := int64(0)

	if recursive {
		// 递归：filepath.WalkDir
		filepath.WalkDir(dir, func(path string, d os.DirEntry, err error) error {
			if err != nil {
				return nil // 忽略权限错误
			}
			if !d.IsDir() {
				if info, e := d.Info(); e == nil && info.Mode().IsRegular() {
					fileCount++
					totalBytes += info.Size()
				}
			}
			return nil
		})
	} else {
		// 非递归：os.ReadDir 一层
		entries, err := os.ReadDir(dir)
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		for _, entry := range entries {
			if !entry.IsDir() {
				if info, e := entry.Info(); e == nil && info.Mode().IsRegular() {
					fileCount++
					totalBytes += info.Size()
				}
			}
		}
	}

	writeJSON(w, map[string]interface{}{
		"dir":         dir,
		"recursive":   recursive,
		"files":       fileCount,
		"total_bytes": totalBytes,
	})
}

// ==================== 工具函数 ====================

func contentToString(v interface{}) string {
	switch val := v.(type) {
	case string:
		return val
	default:
		// 规范 JSON：紧凑分隔符、非 ASCII 不转义、HTML 字符不转义
		// （json.Marshal 默认把 < > & 转义成 \u003c，与其余四门不一致）
		var buf bytes.Buffer
		enc := json.NewEncoder(&buf)
		enc.SetEscapeHTML(false)
		if err := enc.Encode(val); err != nil {
			return fmt.Sprintf("%v", val)
		}
		return strings.TrimRight(buf.String(), "\n")
	}
}

func writeJSON(w http.ResponseWriter, v interface{}) {
	// 与 contentToString 同理：Encoder + SetEscapeHTML(false)，
	// 否则读回的内容里 < > & 会变成 \u003c 等转义序列，五门语言对不上。
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false)
	if err := enc.Encode(v); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	w.Write(buf.Bytes())
}

// ==================== main ====================

func main() {
	mux := http.NewServeMux()
	mux.HandleFunc("/file/write", writeHandler)
	mux.HandleFunc("/file/read", readHandler)
	mux.HandleFunc("/file/scan", scanHandler)

	log.Printf("[Go] file-io server starting on %s", listenAddr)
	if err := http.ListenAndServe(listenAddr, mux); err != nil {
		log.Fatalf("server failed: %v", err)
	}
}
