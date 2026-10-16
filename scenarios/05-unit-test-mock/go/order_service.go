// Package unittest 场景 05：单元测试 & Mock — Go 实现
//
// Go 测试框架特点：
// 1. 标准库 `testing`，零外部依赖
// 2. 测试文件 *_test.go 放在同目录
// 3. Mock 模式：定义 interface，真实实现 + Mock 实现（Go 没有类继承）
// 4. go test -cover 原生覆盖率
// 5. go test -race 原生竞态检测
//
// 和 Java Mockito 对比：
// - Java Mockito 用反射动态 Mock，Go 靠接口注入替换实现
// - Go 没有 @Mock，自己写 Mock 结构体实现接口
// - 但 Go 更简单、更显式
package unittest

import (
	"errors"
	"fmt"
)

// ==================== 业务模型 ====================

type Product struct {
	Name     string
	Price    float64
	Quantity int
}

type Order struct {
	CustomerID string
	Products   []Product
	CouponCode string
}

type CheckoutResult struct {
	Success    bool
	PaymentID  string
	FinalPrice float64
	Error      string
}

// PaymentService 外部支付接口 — 真实实现会调第三方，测试时用 Mock
//
// Go 没有类继承，Mock 的经典模式就是：定义 interface → 真实 struct 实现它 → Mock struct 也实现它
type PaymentService interface {
	Pay(customerID string, amount float64) (string, error)
}

// OrderService 被测业务类
type OrderService struct {
	Payment PaymentService // 接口注入，方便替换 Mock
}

func NewOrderService(payment PaymentService) *OrderService {
	return &OrderService{Payment: payment}
}

// CalculateTotal 计算订单总价
func (s *OrderService) CalculateTotal(products []Product) float64 {
	if len(products) == 0 {
		return 0
	}
	var total float64
	for _, p := range products {
		total += p.Price * float64(p.Quantity)
	}
	return total
}

// ApplyDiscount 应用优惠券折扣
// 支持：SAVE50（满100减50）/ DISCOUNT10（9折）/ DISCOUNT20（8折）
func (s *OrderService) ApplyDiscount(total float64, couponCode string) (float64, error) {
	if total <= 0 {
		return 0, nil
	}
	if couponCode == "" {
		return total, nil
	}

	switch couponCode {
	case "SAVE50":
		if total >= 100 {
			return total - 50, nil
		}
		return total, nil
	case "DISCOUNT10":
		return total * 0.9, nil
	case "DISCOUNT20":
		return total * 0.8, nil
	default:
		return 0, fmt.Errorf("无效的优惠券码: %s", couponCode)
	}
}

// Checkout 下单结账
func (s *OrderService) Checkout(order *Order) CheckoutResult {
	if order == nil || len(order.Products) == 0 {
		return CheckoutResult{Success: false, Error: "订单为空"}
	}

	total := s.CalculateTotal(order.Products)
	finalPrice, err := s.ApplyDiscount(total, order.CouponCode)
	if err != nil {
		return CheckoutResult{Success: false, Error: err.Error()}
	}

	paymentID, err := s.Payment.Pay(order.CustomerID, finalPrice)
	if err != nil {
		return CheckoutResult{Success: false, Error: "支付失败: " + err.Error()}
	}

	return CheckoutResult{
		Success:    true,
		PaymentID:  paymentID,
		FinalPrice: finalPrice,
	}
}

// ==================== Mock 实现（测试代码会用，这里也提供一个） ====================

// MockPayment 测试用的 Mock PaymentService 实现
type MockPayment struct {
	PayResult string
	PayError  error
	Calls     int // 记录被调用次数
}

func (m *MockPayment) Pay(customerID string, amount float64) (string, error) {
	m.Calls++
	return m.PayResult, m.PayError
}

// RealPayment 真实实现（演示用）
type RealPayment struct{}

func (r *RealPayment) Pay(customerID string, amount float64) (string, error) {
	// 真实实现会调第三方支付网关
	return "", errors.New("真实支付不可用，请用 Mock")
}
