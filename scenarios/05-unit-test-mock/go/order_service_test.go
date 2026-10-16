package unittest

import (
	"errors"
	"fmt"
	"testing"
)

// 场景 05：单元测试 — Go 实现（标准库 testing + 接口 Mock）
//
// Go 测试特点：
// 1. 标准库 testing，零依赖
// 2. 测试函数以 Test 开头，参数 *testing.T
// 3. Mock 直接写一个 struct 实现 PaymentService 接口
// 4. t.Run 做子测试（相当于 Java 的 @Nested）
// 5. go test -v -race -cover ./... 一键跑

// ============ CalculateTotal ============

func TestCalculateTotal(t *testing.T) {
	svc := NewOrderService(&MockPayment{})

	tests := []struct {
		name     string
		products []Product
		want     float64
	}{
		{
			name:     "正常计算多个产品",
			products: []Product{{Name: "苹果", Price: 10, Quantity: 2}, {Name: "香蕉", Price: 5, Quantity: 3}},
			want:     35,
		},
		{
			name:     "空列表返回 0",
			products: []Product{},
			want:     0,
		},
		{
			name:     "nil 切片返回 0",
			products: nil,
			want:     0,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := svc.CalculateTotal(tt.products)
			if got != tt.want {
				t.Errorf("CalculateTotal() = %v, want %v", got, tt.want)
			}
		})
	}
}

// ============ ApplyDiscount ============

func TestApplyDiscount(t *testing.T) {
	svc := NewOrderService(&MockPayment{})

	tests := []struct {
		name     string
		total    float64
		coupon   string
		want     float64
		wantErr  bool
	}{
		{"无优惠券返回原价", 100, "", 100, false},
		{"nil 优惠券返回原价", 100, "", 100, false},
		{"SAVE50 满100减50", 100, "SAVE50", 50, false},
		{"SAVE50 不满100不减", 80, "SAVE50", 80, false},
		{"DISCOUNT10 九折", 100, "DISCOUNT10", 90, false},
		{"DISCOUNT20 八折", 100, "DISCOUNT20", 80, false},
		{"无效优惠券报错", 100, "INVALID", 0, true},
		{"零总价返回0", 0, "SAVE50", 0, false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := svc.ApplyDiscount(tt.total, tt.coupon)
			if (err != nil) != tt.wantErr {
				t.Errorf("ApplyDiscount() error = %v, wantErr %v", err, tt.wantErr)
				return
			}
			if !tt.wantErr && got != tt.want {
				t.Errorf("ApplyDiscount() = %v, want %v", got, tt.want)
			}
		})
	}
}

// ============ Checkout（带 Mock） ============

func TestCheckout(t *testing.T) {
	t.Run("支付成功返回 paymentId", func(t *testing.T) {
		mock := &MockPayment{PayResult: "PAY-12345", PayError: nil}
		svc := NewOrderService(mock)

		order := &Order{
			CustomerID: "customer-001",
			Products:   []Product{{Name: "苹果", Price: 10, Quantity: 10}},
			CouponCode: "DISCOUNT10",
		}

		result := svc.Checkout(order)

		if !result.Success {
			t.Fatalf("expected success, got error: %s", result.Error)
		}
		if result.PaymentID != "PAY-12345" {
			t.Errorf("PaymentID = %v, want PAY-12345", result.PaymentID)
		}
		if result.FinalPrice != 90 {
			t.Errorf("FinalPrice = %v, want 90", result.FinalPrice)
		}
		if mock.Calls != 1 {
			t.Errorf("Payment.Pay 被调用 %d 次，期望 1 次", mock.Calls)
		}
	})

	t.Run("支付失败返回错误信息", func(t *testing.T) {
		mock := &MockPayment{PayError: errors.New("余额不足")}
		svc := NewOrderService(mock)

		order := &Order{
			CustomerID: "customer-001",
			Products:   []Product{{Name: "苹果", Price: 10, Quantity: 10}},
		}

		result := svc.Checkout(order)

		if result.Success {
			t.Fatal("expected failure")
		}
		if result.Error == "" {
			t.Error("expected error message")
		}
	})

	t.Run("空订单返回失败", func(t *testing.T) {
		mock := &MockPayment{}
		svc := NewOrderService(mock)

		order := &Order{CustomerID: "customer-001"} // Products 为空

		result := svc.Checkout(order)

		if result.Success {
			t.Fatal("expected failure")
		}
		if mock.Calls != 0 {
			t.Errorf("Payment.Pay 不应被调用，实际 %d 次", mock.Calls)
		}
	})

	t.Run("nil 订单返回失败", func(t *testing.T) {
		mock := &MockPayment{}
		svc := NewOrderService(mock)

		result := svc.Checkout(nil)

		if result.Success {
			t.Fatal("expected failure")
		}
	})
}

// ============ Benchmark（性能对比用） ============

func BenchmarkCalculateTotal(b *testing.B) {
	svc := NewOrderService(&MockPayment{})
	products := make([]Product, 100)
	for i := range products {
		products[i] = Product{Price: 10, Quantity: 1}
	}
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		svc.CalculateTotal(products)
	}
}

func ExampleNewOrderService() {
	mock := &MockPayment{PayResult: "PAY-001"}
	svc := NewOrderService(mock)
	result := svc.Checkout(&Order{
		CustomerID: "demo",
		Products:   []Product{{Name: "book", Price: 59.9, Quantity: 1}},
	})
	fmt.Println(result.Success)
	// Output: true
}
