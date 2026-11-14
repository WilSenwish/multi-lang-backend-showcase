// Package main 场景 11：数据库 CRUD + 连接池 — Go 实现
//
// Go DB 特点：
// 1. database/sql + GORM（最流行的 ORM）
// 2. database/sql 内置连接池：SetMaxOpenConns / SetMaxIdleConns / SetConnMaxLifetime
// 3. SQLite 驱动：github.com/mattn/go-sqlite3 或纯 Go 版本 glebarez/sqlite
// 4. GORM 链式 API + 自动迁移 AutoMigrate
//
// 和 Java Spring Data JPA 对比：
// - GORM 有 CodeFirst（AutoMigrate 自动建表）
// - Go 结构体 tag 定义映射
// - database/sql 连接池是标准库，不需要额外组件

package main

import (
	"fmt"
	"net/http"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/glebarez/sqlite"
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
	"gorm.io/gorm"
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

const listenAddr = ":8126"

// ==================== 数据模型 ====================

type User struct {
	ID        uint      `json:"id" gorm:"primaryKey"`
	Name      string    `json:"name" gorm:"size:64;not null"`
	Email     string    `json:"email" gorm:"size:128"`
	Age       int       `json:"age"`
	CreatedAt time.Time `json:"created_at"`
}

// TableName GORM 可以通过这个自定义表名
func (User) TableName() string { return "users" }

// ==================== 全局 DB ====================

var db *gorm.DB

func initDB() {
	var err error
	db, err = gorm.Open(sqlite.Open("demo.db"), &gorm.Config{})
	if err != nil {
		logger.Fatalw("DB 连接失败", "error", err)
	}

	// 自动迁移（CodeFirst，自动建表）
	if err := db.AutoMigrate(&User{}); err != nil {
		logger.Fatalw("AutoMigrate 失败", "error", err)
	}

	// 配置连接池（database/sql 内置）
	sqlDB, _ := db.DB()
	sqlDB.SetMaxOpenConns(10)  // 最大打开连接数
	sqlDB.SetMaxIdleConns(2)   // 最大空闲连接数
	sqlDB.SetConnMaxLifetime(5 * time.Minute)

	logger.Infow("DB 初始化成功", "db", "SQLite", "file", "demo.db")
}

// ==================== API ====================

type UserInput struct {
	Name  *string `json:"name"`
	Email *string `json:"email"`
	Age   *int    `json:"age"`
}

func createUser(c *gin.Context) {
	var input struct {
		Name  string `json:"name"`
		Email string `json:"email"`
		Age   int    `json:"age"`
	}
	if err := c.ShouldBindJSON(&input); err != nil {
		c.JSON(400, gin.H{"error": "invalid json: " + err.Error()})
		return
	}

	user := User{Name: input.Name, Email: input.Email, Age: input.Age}
	if err := db.Create(&user).Error; err != nil {
		logger.Errorw("create user failed", "error", err)
		c.JSON(400, gin.H{"error": err.Error()})
		return
	}
	c.JSON(201, user)
}

func listUsers(c *gin.Context) {
	page, _ := strconv.Atoi(c.DefaultQuery("page", "0"))
	size, _ := strconv.Atoi(c.DefaultQuery("size", "10"))
	if page < 0 {
		page = 0
	}
	if size <= 0 {
		size = 10
	}

	var items []User
	var total int64

	db.Model(&User{}).Count(&total)
	db.Order("id ASC").Offset(page * size).Limit(size).Find(&items)

	c.JSON(200, gin.H{
		"items": items,
		"total": total,
		"page":  page,
		"size":  size,
	})
}

func getUser(c *gin.Context) {
	idStr := c.Param("id")
	id, err := strconv.ParseUint(idStr, 10, 64)
	if err != nil {
		c.JSON(400, gin.H{"error": "invalid id"})
		return
	}

	var user User
	if err := db.First(&user, id).Error; err != nil {
		c.JSON(404, gin.H{"error": "not found"})
		return
	}
	c.JSON(200, user)
}

func updateUser(c *gin.Context) {
	idStr := c.Param("id")
	id, err := strconv.ParseUint(idStr, 10, 64)
	if err != nil {
		c.JSON(400, gin.H{"error": "invalid id"})
		return
	}

	var input UserInput
	if err := c.ShouldBindJSON(&input); err != nil {
		c.JSON(400, gin.H{"error": "invalid json: " + err.Error()})
		return
	}

	var user User
	if err := db.First(&user, id).Error; err != nil {
		c.JSON(404, gin.H{"error": "not found"})
		return
	}

	if input.Name != nil {
		user.Name = *input.Name
	}
	if input.Email != nil {
		user.Email = *input.Email
	}
	if input.Age != nil {
		user.Age = *input.Age
	}

	db.Save(&user)
	c.JSON(200, user)
}

func deleteUser(c *gin.Context) {
	idStr := c.Param("id")
	id, err := strconv.ParseUint(idStr, 10, 64)
	if err != nil {
		c.JSON(400, gin.H{"error": "invalid id"})
		return
	}

	result := db.Delete(&User{}, id)
	if result.Error != nil || result.RowsAffected == 0 {
		c.JSON(404, gin.H{"error": "not found"})
		return
	}
	c.Status(http.StatusNoContent)
}

// ==================== main ====================

func main() {
	defer logger.Sync() // flush 日志

	initDB()

	r := gin.Default() // 自带 Recovery + Logger 中间件
	r.POST("/users", createUser)
	r.GET("/users", listUsers)
	r.GET("/users/:id", getUser)
	r.PUT("/users/:id", updateUser)
	r.DELETE("/users/:id", deleteUser)
	r.GET("/health", func(c *gin.Context) {
		c.JSON(200, gin.H{"service": "db-crud-pool-go", "db": "sqlite"})
	})

	logger.Infow("server starting", "addr", listenAddr)
	if err := r.Run(listenAddr); err != nil {
		logger.Fatalw("server failed", "error", err)
	}
}
