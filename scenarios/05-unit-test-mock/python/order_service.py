"""
场景 05：单元测试 & Mock — Python 实现（pytest + unittest.mock）

Python 测试框架特点：
1. pytest 是 Python 生态事实标准（比原生 unittest 好用）
2. unittest.mock 标准库自带 Mock/Patch
3. pytest-cov 生成覆盖率
4. pytest fixture 自动注入、参数化测试
5. @pytest.mark.parametrize 批量跑多组参数

和 Java / Go 对比：
- Python 测试代码更短、更简洁（动态类型 + pytest fixture）
- Mock 方式灵活：mock.patch 可以 patch 任何函数/方法
- 但没有编译期检查，写错了只能运行时报错
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Product:
    name: str
    price: float
    quantity: int


@dataclass
class Order:
    customer_id: str
    products: List[Product] = field(default_factory=list)
    coupon_code: Optional[str] = None


@dataclass
class CheckoutResult:
    success: bool
    payment_id: Optional[str] = None
    final_price: float = 0
    error: Optional[str] = None


class PaymentService:
    """外部支付接口 — 真实实现会调第三方"""
    def pay(self, customer_id: str, amount: float) -> str:
        raise NotImplementedError("真实支付不可用，请 Mock")


class OrderService:
    def __init__(self, payment: PaymentService):
        self.payment = payment

    # ============ 业务方法 ============

    def calculate_total(self, products: List[Product]) -> float:
        if not products:
            return 0.0
        return sum(p.price * p.quantity for p in products)

    def apply_discount(self, total: float, coupon_code: Optional[str]) -> tuple[float, Optional[str]]:
        """返回 (折扣后价格, 错误信息)"""
        if total <= 0:
            return 0.0, None
        if not coupon_code:
            return total, None

        coupon = coupon_code.upper()
        if coupon == "SAVE50":
            return (total - 50) if total >= 100 else total, None
        elif coupon == "DISCOUNT10":
            return total * 0.9, None
        elif coupon == "DISCOUNT20":
            return total * 0.8, None
        else:
            return 0.0, f"无效的优惠券码: {coupon_code}"

    def checkout(self, order: Optional[Order]) -> CheckoutResult:
        if order is None or not order.products:
            return CheckoutResult(success=False, error="订单为空")

        total = self.calculate_total(order.products)
        final_price, err = self.apply_discount(total, order.coupon_code)
        if err:
            return CheckoutResult(success=False, error=err)

        try:
            payment_id = self.payment.pay(order.customer_id, final_price)
            return CheckoutResult(success=True, payment_id=payment_id, final_price=final_price)
        except Exception as e:
            return CheckoutResult(success=False, error=f"支付失败: {e}")
