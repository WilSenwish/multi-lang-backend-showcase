//! 场景 05：单元测试 & Mock — Rust 实现
//!
//! Rust 测试框架特点：
//! 1. 内置 #[test] + #[cfg(test)] 模块，cargo test 直接跑
//! 2. mockall crate 做 Mock（derive(Mock) 宏生成 Mock 结构体）
//! 3. cargo test -- --nocapture 可以看 println! 输出
//! 4. 覆盖率：cargo-llvm-cov 或 tarpaulin
//! 5. 编译器强制处理 Result，不会漏错误
//!
//! 和 Java Mockito / Python mock 对比：
//! - Rust Mock 是编译期生成的，没有运行时反射开销
//! - 类型安全：Mock 结构体和真实结构体有同样的 trait bound
//! - 但 mockall 需要 nightly 的 proc_macro（或稳定版的 mockall_derive）

// ============ 业务模型 ============

#[derive(Debug, Clone)]
pub struct Product {
    pub name: String,
    pub price: f64,
    pub quantity: u32,
}

#[derive(Debug, Clone)]
pub struct Order {
    pub customer_id: String,
    pub products: Vec<Product>,
    pub coupon_code: Option<String>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct CheckoutResult {
    pub success: bool,
    pub payment_id: Option<String>,
    pub final_price: f64,
    pub error: Option<String>,
}

// ============ 外部依赖 trait（方便 Mock） ============

/// 支付服务接口
/// Mockall 在测试里会自动生成 MockPayment
#[cfg(test)]
use mockall::automock;

#[cfg_attr(test, automock)]
pub trait PaymentService {
    fn pay(&self, customer_id: &str, amount: f64) -> Result<String, String>;
}

// ============ 业务类 ============

pub struct OrderService {
    payment: Box<dyn PaymentService>,
}

impl OrderService {
    pub fn new(payment: Box<dyn PaymentService>) -> Self {
        Self { payment }
    }

    /// 计算订单总价
    pub fn calculate_total(&self, products: &[Product]) -> f64 {
        if products.is_empty() {
            return 0.0;
        }
        products.iter().map(|p| p.price * p.quantity as f64).sum()
    }

    /// 应用优惠券折扣，返回 (价格, None) 或 (0, Some(error))
    pub fn apply_discount(&self, total: f64, coupon_code: Option<&str>) -> Result<f64, String> {
        if total <= 0.0 {
            return Ok(0.0);
        }
        match coupon_code {
            None | Some("") => Ok(total),
            Some(code) => match code.to_uppercase().as_str() {
                "SAVE50" => Ok(if total >= 100.0 { total - 50.0 } else { total }),
                "DISCOUNT10" => Ok(total * 0.9),
                "DISCOUNT20" => Ok(total * 0.8),
                other => Err(format!("无效的优惠券码: {}", other)),
            },
        }
    }

    /// 下单结账
    pub fn checkout(&self, order: &Option<Order>) -> CheckoutResult {
        let order = match order {
            Some(o) => o,
            None => return CheckoutResult { success: false, payment_id: None, final_price: 0.0, error: Some("订单为空".into()) },
        };
        if order.products.is_empty() {
            return CheckoutResult { success: false, payment_id: None, final_price: 0.0, error: Some("订单为空".into()) };
        }

        let total = self.calculate_total(&order.products);
        let final_price = match self.apply_discount(total, order.coupon_code.as_deref()) {
            Ok(p) => p,
            Err(e) => return CheckoutResult { success: false, payment_id: None, final_price: 0.0, error: Some(e) },
        };

        match self.payment.pay(&order.customer_id, final_price) {
            Ok(id) => CheckoutResult {
                success: true,
                payment_id: Some(id),
                final_price,
                error: None,
            },
            Err(e) => CheckoutResult {
                success: false,
                payment_id: None,
                final_price,
                error: Some(format!("支付失败: {}", e)),
            },
        }
    }
}

// ============ 测试 ============

#[cfg(test)]
mod tests {
    use super::*;
    use mockall::predicate::*;

    fn make_service(mock: MockPaymentService) -> OrderService {
        OrderService::new(Box::new(mock))
    }

    // ---- calculate_total ----

    #[test]
    fn test_calculate_total_multiple() {
        let mock = MockPaymentService::new();
        let svc = make_service(mock);
        let products = vec![
            Product { name: "苹果".into(), price: 10.0, quantity: 2 },
            Product { name: "香蕉".into(), price: 5.0, quantity: 3 },
        ];
        assert_eq!(svc.calculate_total(&products), 35.0);
    }

    #[test]
    fn test_calculate_total_empty() {
        let mock = MockPaymentService::new();
        let svc = make_service(mock);
        assert_eq!(svc.calculate_total(&[]), 0.0);
    }

    // ---- apply_discount ----

    #[test]
    fn test_apply_discount_no_coupon() {
        let mock = MockPaymentService::new();
        let svc = make_service(mock);
        assert_eq!(svc.apply_discount(100.0, None).unwrap(), 100.0);
        assert_eq!(svc.apply_discount(100.0, Some("")).unwrap(), 100.0);
    }

    #[test]
    fn test_apply_discount_save50() {
        let mock = MockPaymentService::new();
        let svc = make_service(mock);
        assert_eq!(svc.apply_discount(100.0, Some("SAVE50")).unwrap(), 50.0);
        assert_eq!(svc.apply_discount(80.0, Some("SAVE50")).unwrap(), 80.0);
    }

    #[test]
    fn test_apply_discount_invalid() {
        let mock = MockPaymentService::new();
        let svc = make_service(mock);
        assert!(svc.apply_discount(100.0, Some("INVALID")).is_err());
    }

    // ---- checkout（带 Mock PaymentService）----

    #[test]
    fn test_checkout_success() {
        let mut mock = MockPaymentService::new();
        mock.expect_pay()
            .with(eq("customer-001"), eq(90.0))
            .times(1)
            .returning(|_, _| Ok("PAY-12345".into()));

        let svc = make_service(mock);
        let order = Order {
            customer_id: "customer-001".into(),
            products: vec![Product { name: "苹果".into(), price: 10.0, quantity: 10 }],
            coupon_code: Some("DISCOUNT10".into()),
        };

        let result = svc.checkout(&Some(order));
        assert!(result.success);
        assert_eq!(result.payment_id.as_deref(), Some("PAY-12345"));
        assert_eq!(result.final_price, 90.0);
    }

    #[test]
    fn test_checkout_payment_failure() {
        let mut mock = MockPaymentService::new();
        mock.expect_pay()
            .returning(|_, _| Err("余额不足".into()));

        let svc = make_service(mock);
        let order = Order {
            customer_id: "customer-001".into(),
            products: vec![Product { name: "苹果".into(), price: 10.0, quantity: 10 }],
            coupon_code: None,
        };

        let result = svc.checkout(&Some(order));
        assert!(!result.success);
        assert!(result.error.as_ref().unwrap().contains("余额不足"));
    }

    #[test]
    fn test_checkout_empty_order() {
        let mock = MockPaymentService::new(); // 不会被调用
        let svc = make_service(mock);
        let order = Order { customer_id: "x".into(), products: vec![], coupon_code: None };

        let result = svc.checkout(&Some(order));
        assert!(!result.success);
    }

    #[test]
    fn test_checkout_none_order() {
        let mock = MockPaymentService::new();
        let svc = make_service(mock);

        let result = svc.checkout(&None);
        assert!(!result.success);
    }
}
