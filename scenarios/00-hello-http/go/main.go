// Package main scenarios/00-hello-http Go 实现
// 统一 API 契约:
//
//	GET /hello?name={xxx}
//	→ {"msg": "hello {xxx}"}
//	→ {"msg": "hello world"}  // name 缺省
package main

import (
	"encoding/json"
	"log"
	"net/http"
)

// HelloResponse 统一响应结构
type HelloResponse struct {
	Msg string `json:"msg"`
}

const (
	defaultName = "world"
	listenAddr  = ":8081"
)

func helloHandler(w http.ResponseWriter, r *http.Request) {
	// 只支持 GET
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	// 获取 name 参数
	name := r.URL.Query().Get("name")
	if name == "" {
		name = defaultName
	}

	// 构建响应
	resp := HelloResponse{Msg: "hello " + name}

	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	if err := json.NewEncoder(w).Encode(resp); err != nil {
		log.Printf("encode response error: %v", err)
	}
}

func main() {
	mux := http.NewServeMux()
	mux.HandleFunc("/hello", helloHandler)

	log.Printf("[Go] hello-http server starting on %s", listenAddr)
	if err := http.ListenAndServe(listenAddr, mux); err != nil {
		log.Fatalf("server failed: %v", err)
	}
}
