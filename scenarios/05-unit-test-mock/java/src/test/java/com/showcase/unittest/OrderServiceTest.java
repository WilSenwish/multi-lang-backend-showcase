package com.showcase.unittest;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.math.BigDecimal;
import java.util.Arrays;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;

/**
 * 场景 05：单元测试 — Java 实现（JUnit 5 + Mockito）
 *
 * Java 测试框架特点：
 * 1. JUnit 5 是当前标准（@Test / @Nested / @DisplayName / @BeforeEach）
 * 2. Mockito Mock 外部依赖（PaymentService.pay）
 * 3. @ExtendWith(MockitoExtension.class) 自动注入 @Mock
 * 4. JaCoCo 自动生成覆盖率报告（target/site/jacoco/index.html）
 *
 * 和 Go / Python / Rust / TS 对比：
 * - Java Mock 最成熟（Mockito/PowerMock/Spring Mock）
 * - 测试代码也是强类型，编译期能查错
 * - 运行命令：mvn test / mvn jacoco:report
 */
@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    private OrderService orderService;

    @Mock
    private OrderService.PaymentService paymentService;

    @BeforeEach
    void setUp() {
        orderService = new OrderService(paymentService);
    }

    // ============ calculateTotal ============

    @Nested
    @DisplayName("calculateTotal 计算总价")
    class CalculateTotal {

        @Test
        @DisplayName("正常计算多个产品")
        void shouldCalculateMultipleProducts() {
            List<OrderService.Product> products = List.of(
                    new OrderService.Product("苹果", new BigDecimal("10"), 2),
                    new OrderService.Product("香蕉", new BigDecimal("5"), 3)
            );
            BigDecimal result = orderService.calculateTotal(products);
            assertEquals(new BigDecimal("35"), result); // 10*2 + 5*3 = 35
        }

        @Test
        @DisplayName("空列表返回 0")
        void shouldReturnZeroForEmptyList() {
            assertEquals(BigDecimal.ZERO, orderService.calculateTotal(List.of()));
        }

        @Test
        @DisplayName("null 列表返回 0")
        void shouldReturnZeroForNullList() {
            assertEquals(BigDecimal.ZERO, orderService.calculateTotal(null));
        }

        @Test
        @DisplayName("null 产品被跳过")
        void shouldSkipNullProduct() {
            // List.of 不允许 null 元素, 用 Arrays.asList 才能构造含 null 的列表来验证跳过逻辑
            List<OrderService.Product> products = Arrays.asList(
                    null,
                    new OrderService.Product("苹果", new BigDecimal("10"), 2)
            );
            assertEquals(new BigDecimal("20"), orderService.calculateTotal(products));
        }
    }

    // ============ applyDiscount ============

    @Nested
    @DisplayName("applyDiscount 优惠券折扣")
    class ApplyDiscount {

        @Test
        @DisplayName("无优惠券返回原价")
        void shouldReturnOriginalWhenNoCoupon() {
            BigDecimal total = new BigDecimal("100");
            assertEquals(total, orderService.applyDiscount(total, null));
            assertEquals(total, orderService.applyDiscount(total, ""));
            assertEquals(total, orderService.applyDiscount(total, "  "));
        }

        @Test
        @DisplayName("满减优惠券 SAVE50（满 100 减 50）")
        void shouldApplySave50() {
            // 满 100 减 50
            assertEquals(new BigDecimal("50"), orderService.applyDiscount(new BigDecimal("100"), "SAVE50"));
            // 不满 100 不减
            assertEquals(new BigDecimal("80"), orderService.applyDiscount(new BigDecimal("80"), "SAVE50"));
        }

        @Test
        @DisplayName("折扣优惠券 DISCOUNT10（9 折）")
        void shouldApplyDiscount10() {
            BigDecimal result = orderService.applyDiscount(new BigDecimal("100"), "DISCOUNT10");
            assertEquals(0, new BigDecimal("90").compareTo(result));
        }

        @Test
        @DisplayName("折扣优惠券 DISCOUNT20（8 折）")
        void shouldApplyDiscount20() {
            BigDecimal result = orderService.applyDiscount(new BigDecimal("100"), "DISCOUNT20");
            assertEquals(0, new BigDecimal("80").compareTo(result));
        }

        @Test
        @DisplayName("无效优惠券抛异常")
        void shouldThrowForInvalidCoupon() {
            assertThrows(IllegalArgumentException.class,
                    () -> orderService.applyDiscount(new BigDecimal("100"), "INVALID"));
        }
    }

    // ============ checkout（带 Mock PaymentService） ============

    @Nested
    @DisplayName("checkout 下单结账（Mock 外部依赖）")
    class Checkout {

        @Test
        @DisplayName("支付成功返回 paymentId")
        void shouldReturnPaymentIdWhenSuccess() {
            // Mock: PaymentService.pay 返回 "PAY-12345"
            when(paymentService.pay(eq("customer-001"), any(BigDecimal.class)))
                    .thenReturn("PAY-12345");

            OrderService.Order order = new OrderService.Order(
                    "customer-001",
                    List.of(new OrderService.Product("苹果", new BigDecimal("10"), 10)),
                    "DISCOUNT10"
            );

            OrderService.CheckoutResult result = orderService.checkout(order);

            assertTrue(result.isSuccess());
            assertEquals("PAY-12345", result.getPaymentId());
            assertEquals(0, new BigDecimal("90").compareTo(result.getFinalPrice()));

            // 验证 PaymentService.pay 确实被调用了一次
            verify(paymentService, times(1)).pay(eq("customer-001"), any(BigDecimal.class));
        }

        @Test
        @DisplayName("支付失败返回错误信息")
        void shouldReturnErrorWhenPaymentFails() {
            // Mock: PaymentService.pay 抛异常
            when(paymentService.pay(any(), any()))
                    .thenThrow(new RuntimeException("余额不足"));

            OrderService.Order order = new OrderService.Order(
                    "customer-001",
                    List.of(new OrderService.Product("苹果", new BigDecimal("10"), 10)),
                    null
            );

            OrderService.CheckoutResult result = orderService.checkout(order);

            assertFalse(result.isSuccess());
            assertNotNull(result.getError());
            assertTrue(result.getError().contains("余额不足"));
        }

        @Test
        @DisplayName("空订单返回失败")
        void shouldFailForEmptyOrder() {
            OrderService.Order order = new OrderService.Order("customer-001", null, null);
            OrderService.CheckoutResult result = orderService.checkout(order);

            assertFalse(result.isSuccess());
            // PaymentService.pay 不应被调用
            verify(paymentService, never()).pay(any(), any());
        }
    }
}
