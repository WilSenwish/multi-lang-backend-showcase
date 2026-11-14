// Package main scenarios/00-hello-http Go 实现
// 统一 API 契约:
//
//	GET /hello?name={xxx}
//	→ {"msg": "hello {xxx}"}
//	→ {"msg": "hello world"}  // name 缺省
package main

import (
	"fmt"
	"net/http"

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

// HelloResponse 统一响应结构
type HelloResponse struct {
	Msg string `json:"msg"`
}

const (
	defaultName = "world"
	listenAddr  = ":8081"
)

func helloHandler(c *gin.Context) {
	name := c.DefaultQuery("name", defaultName)
	resp := HelloResponse{Msg: "hello " + name}

	logger.Debugw("hello handler called", "name", name)
	c.JSON(http.StatusOK, resp)
}

func main() {
	defer logger.Sync() // flush 日志

	r := gin.Default() // 自带 Recovery + Logger 中间件
	r.GET("/hello", helloHandler)

	logger.Infow("server starting", "addr", listenAddr)
	if err := r.Run(listenAddr); err != nil {
		logger.Fatalw("server failed", "error", err)
	}
}
