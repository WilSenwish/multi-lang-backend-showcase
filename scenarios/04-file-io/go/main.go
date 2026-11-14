package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"

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
func writeHandler(c *gin.Context) {
	var req WriteRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(400, gin.H{"error": "invalid json: " + err.Error()})
		return
	}

	resp := map[string]interface{}{}

	// 把 content 转成字符串写入
	content := contentToString(req.Content)
	// 确保父目录存在
	if dir := filepath.Dir(req.Path); dir != "." && dir != "/" {
		if err := os.MkdirAll(dir, 0755); err != nil {
			logger.Warnw("mkdir failed", "dir", dir, "error", err)
		}
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
		logger.Errorw("write file failed", "path", req.Path, "error", err)
		resp["success"] = false
		resp["error"] = err.Error()
	} else {
		resp["success"] = true
		resp["path"] = req.Path
		resp["bytes_written"] = len(content)
		resp["append"] = req.Append
	}

	writeJSON(c, 200, resp)
}

// GET /file/read
func readHandler(c *gin.Context) {
	path := c.Query("path")
	if path == "" {
		c.JSON(400, gin.H{"error": "missing path param"})
		return
	}

	info, err := os.Stat(path)
	if err != nil {
		if os.IsNotExist(err) {
			c.JSON(404, gin.H{"error": "文件不存在: " + path})
		} else {
			c.JSON(500, gin.H{"error": err.Error()})
		}
		return
	}
	if info.IsDir() {
		c.JSON(400, gin.H{"error": "不是文件: " + path})
		return
	}

	data, err := os.ReadFile(path)
	if err != nil {
		c.JSON(500, gin.H{"error": err.Error()})
		return
	}

	writeJSON(c, 200, map[string]interface{}{
		"path":    path,
		"content": string(data),
		"bytes":   len(data),
	})
}

// GET /file/scan
func scanHandler(c *gin.Context) {
	dir := c.Query("dir")
	if dir == "" {
		c.JSON(400, gin.H{"error": "missing dir param"})
		return
	}
	recursive := c.DefaultQuery("recursive", "true") != "false" // 默认 true

	info, err := os.Stat(dir)
	if err != nil {
		if os.IsNotExist(err) {
			c.JSON(404, gin.H{"error": "目录不存在: " + dir})
		} else {
			c.JSON(500, gin.H{"error": err.Error()})
		}
		return
	}
	if !info.IsDir() {
		c.JSON(400, gin.H{"error": "不是目录: " + dir})
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
			c.JSON(500, gin.H{"error": err.Error()})
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

	writeJSON(c, 200, map[string]interface{}{
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

func writeJSON(c *gin.Context, code int, v interface{}) {
	// 与 contentToString 同理：Encoder + SetEscapeHTML(false)，
	// 否则读回的内容里 < > & 会变成 \u003c 等转义序列，五门语言对不上。
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false)
	if err := enc.Encode(v); err != nil {
		c.JSON(500, gin.H{"error": err.Error()})
		return
	}
	c.Data(code, "application/json; charset=utf-8", buf.Bytes())
}

// ==================== main ====================

func main() {
	defer logger.Sync() // flush 日志

	r := gin.Default() // 自带 Recovery + Logger 中间件
	r.POST("/file/write", writeHandler)
	r.GET("/file/read", readHandler)
	r.GET("/file/scan", scanHandler)

	logger.Infow("server starting", "addr", listenAddr)
	if err := r.Run(listenAddr); err != nil {
		logger.Fatalw("server failed", "error", err)
	}
}
