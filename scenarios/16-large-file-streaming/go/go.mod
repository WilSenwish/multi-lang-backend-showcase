module large-file-streaming

go 1.22

// 本场景刻意只用标准库：net/http + crypto/sha256 + syscall。
// "固定缓冲 + 手写行边界"不需要任何第三方依赖 —— 这正是 Go 在本场景的优势之一。
