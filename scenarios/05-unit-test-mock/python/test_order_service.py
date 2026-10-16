"""场景 05：单元测试 — Python 实现（pytest + unittest.mock）"""
import pytest
from unittest.mock import Mock, MagicMock
from order_service import (
    Product, Order, OrderService, CheckoutResult, PaymentService
)


# ============ Fixture ============

@pytest.fixture
def mock_payment():
    """Mock PaymentService（成功）"""
    mock = MagicMock(spec=PaymentService)
    mock.pay.return_value = "PAY-12345"
    return mock


@pytest.fixture
def order_service(mock_payment):
    return OrderService(mock_payment)


# ============ calculate_total ============

class TestCalculateTotal:
    def test_multiple_products(self, order_service):
        products = [Product("苹果", 10, 2), Product("香蕉", 5, 3)]
        assert order_service.calculate_total(products) == 35

    def test_empty_list(self, order_service):
        assert order_service.calculate_total([]) == 0

    def test_none_list(self, order_service):
        assert order_service.calculate_total(None) == 0


# ============ apply_discount ============

class TestApplyDiscount:
    @pytest.mark.parametrize("coupon_code,total,expected", [
        (None, 100, 100),
        ("", 100, 100),
        ("SAVE50", 100, 50),        # 满 100 减 50
        ("SAVE50", 80, 80),         # 不满 100 不减
        ("DISCOUNT10", 100, 90),    # 九折
        ("DISCOUNT20", 100, 80),    # 八折
    ])
    def test_valid_coupon(self, order_service, coupon_code, total, expected):
        price, err = order_service.apply_discount(total, coupon_code)
        assert err is None
        assert price == expected

    def test_invalid_coupon(self, order_service):
        price, err = order_service.apply_discount(100, "INVALID")
        assert err is not None
        assert "无效" in err


# ============ checkout（带 Mock） ============

class TestCheckout:
    def test_payment_success(self, order_service, mock_payment):
        order = Order(
            customer_id="customer-001",
            products=[Product("苹果", 10, 10)],
            coupon_code="DISCOUNT10",
        )

        result = order_service.checkout(order)

        assert result.success is True
        assert result.payment_id == "PAY-12345"
        assert result.final_price == 90
        mock_payment.pay.assert_called_once_with("customer-001", 90)

    def test_payment_failure(self, order_service, mock_payment):
        mock_payment.pay.side_effect = Exception("余额不足")

        order = Order(
            customer_id="customer-001",
            products=[Product("苹果", 10, 10)],
        )

        result = order_service.checkout(order)

        assert result.success is False
        assert result.error is not None
        assert "余额不足" in result.error

    def test_empty_order(self, order_service, mock_payment):
        order = Order(customer_id="customer-001")

        result = order_service.checkout(order)

        assert result.success is False
        assert result.error == "订单为空"
        mock_payment.pay.assert_not_called()

    def test_none_order(self, order_service, mock_payment):
        result = order_service.checkout(None)

        assert result.success is False
        mock_payment.pay.assert_not_called()
