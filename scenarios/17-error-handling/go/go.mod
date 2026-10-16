module error-handling

go 1.22

// 本场景刻意只用标准库：net/http + errors + encoding/json。
// Go 的错误处理全靠语言内置的两个小机制（error 接口 + %w 包装），
// 不需要任何第三方库 —— 这既是它的优点（零依赖），也是它的代价（code/stack/details 全要自建）。
