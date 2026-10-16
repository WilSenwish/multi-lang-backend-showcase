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
	"encoding/json"
	"log"
	"net/http"
	"strconv"
	"time"

	"github.com/glebarez/sqlite"
	"gorm.io/gorm"
)

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
		log.Fatalf("DB 连接失败: %v", err)
	}

	// 自动迁移（CodeFirst，自动建表）
	if err := db.AutoMigrate(&User{}); err != nil {
		log.Fatalf("AutoMigrate 失败: %v", err)
	}

	// 配置连接池（database/sql 内置）
	sqlDB, _ := db.DB()
	sqlDB.SetMaxOpenConns(10)  // 最大打开连接数
	sqlDB.SetMaxIdleConns(2)   // 最大空闲连接数
	sqlDB.SetConnMaxLifetime(5 * time.Minute)

	log.Printf("[Go] DB 初始化成功（SQLite 文件: demo.db）")
}

// ==================== API ====================

type UserInput struct {
	Name  *string `json:"name"`
	Email *string `json:"email"`
	Age   *int    `json:"age"`
}

func writeJSON(w http.ResponseWriter, code int, v interface{}) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(code)
	json.NewEncoder(w).Encode(v)
}

func usersHandler(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodPost:
		createUser(w, r)
	case http.MethodGet:
		listUsers(w, r)
	default:
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
	}
}

func userHandler(w http.ResponseWriter, r *http.Request) {
	id, err := strconv.ParseUint(r.PathValue("id"), 10, 64)
	if err != nil {
		writeJSON(w, 400, map[string]string{"error": "invalid id"})
		return
	}

	switch r.Method {
	case http.MethodGet:
		getUser(w, uint(id))
	case http.MethodPut:
		updateUser(w, r, uint(id))
	case http.MethodDelete:
		deleteUser(w, uint(id))
	default:
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
	}
}

func createUser(w http.ResponseWriter, r *http.Request) {
	var input struct {
		Name  string `json:"name"`
		Email string `json:"email"`
		Age   int    `json:"age"`
	}
	json.NewDecoder(r.Body).Decode(&input)

	user := User{Name: input.Name, Email: input.Email, Age: input.Age}
	if err := db.Create(&user).Error; err != nil {
		writeJSON(w, 400, map[string]string{"error": err.Error()})
		return
	}
	writeJSON(w, 201, user)
}

func getUser(w http.ResponseWriter, id uint) {
	var user User
	if err := db.First(&user, id).Error; err != nil {
		writeJSON(w, 404, map[string]string{"error": "not found"})
		return
	}
	writeJSON(w, 200, user)
}

func listUsers(w http.ResponseWriter, r *http.Request) {
	page, _ := strconv.Atoi(r.URL.Query().Get("page"))
	size, _ := strconv.Atoi(r.URL.Query().Get("size"))
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

	writeJSON(w, 200, map[string]interface{}{
		"items": items,
		"total": total,
		"page":  page,
		"size":  size,
	})
}

func updateUser(w http.ResponseWriter, r *http.Request, id uint) {
	var input UserInput
	json.NewDecoder(r.Body).Decode(&input)

	var user User
	if err := db.First(&user, id).Error; err != nil {
		writeJSON(w, 404, map[string]string{"error": "not found"})
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
	writeJSON(w, 200, user)
}

func deleteUser(w http.ResponseWriter, id uint) {
	result := db.Delete(&User{}, id)
	if result.Error != nil || result.RowsAffected == 0 {
		writeJSON(w, 404, map[string]string{"error": "not found"})
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// ==================== main ====================

func main() {
	initDB()

	mux := http.NewServeMux()
	mux.HandleFunc("/users", usersHandler)
	mux.HandleFunc("/users/", userHandler)
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, 200, map[string]string{"service": "db-crud-pool-go", "db": "sqlite"})
	})

	log.Printf("[Go] db-crud-pool server starting on %s", listenAddr)
	if err := http.ListenAndServe(listenAddr, mux); err != nil {
		log.Fatalf("server failed: %v", err)
	}
}
