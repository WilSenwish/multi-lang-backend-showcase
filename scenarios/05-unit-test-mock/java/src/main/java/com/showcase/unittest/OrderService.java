package com.showcase.unittest;

import java.math.BigDecimal;
import java.util.List;

/**
 * 被测业务类：OrderService
 *
 * 提供 3 个方法：
 * 1. calculateTotal — 计算订单总价
 * 2. applyDiscount — 应用优惠券折扣
 * 3. checkout — 调用外部 PaymentService（需要 Mock）
 *
 * 这个类的设计刻意没有任何框架依赖，方便测试。
 * Java 测试不需要 Spring Boot — JUnit 5 + Mockito 就够了。
 */
public class OrderService {

    private final PaymentService paymentService;

    /** 构造注入：方便测试时替换 Mock PaymentService */
    public OrderService(PaymentService paymentService) {
        this.paymentService = paymentService;
    }

    /**
     * 计算订单总价 = 所有产品 price × quantity 之和
     *
     * @param products 产品列表
     * @return 总价（BigDecimal）
     */
    public BigDecimal calculateTotal(List<Product> products) {
        if (products == null || products.isEmpty()) {
            return BigDecimal.ZERO;
        }

        BigDecimal total = BigDecimal.ZERO;
        for (Product p : products) {
            if (p == null || p.getPrice() == null) {
                continue; // 跳过 null 产品或 price 为 null
            }
            BigDecimal subtotal = p.getPrice().multiply(BigDecimal.valueOf(p.getQuantity()));
            total = total.add(subtotal);
        }
        return total;
    }

    /**
     * 应用优惠券折扣
     *
     * 支持 3 种优惠券：
     * - 无优惠券（null / 空）→ 原价
     * - 满减：SAVE50（满 100 减 50）
     * - 折扣：DISCOUNT10（打 9 折）、DISCOUNT20（打 8 折）
     *
     * @param total      订单总价
     * @param couponCode 优惠券码
     * @return 折扣后价格
     * @throws IllegalArgumentException 优惠券无效
     */
    public BigDecimal applyDiscount(BigDecimal total, String couponCode) {
        if (total == null || total.compareTo(BigDecimal.ZERO) <= 0) {
            return BigDecimal.ZERO;
        }

        if (couponCode == null || couponCode.isBlank()) {
            return total;
        }

        switch (couponCode.toUpperCase()) {
            case "SAVE50":
                // 满 100 减 50
                if (total.compareTo(new BigDecimal("100")) >= 0) {
                    return total.subtract(new BigDecimal("50"));
                }
                return total;

            case "DISCOUNT10":
                // 9 折
                return total.multiply(new BigDecimal("0.9"));

            case "DISCOUNT20":
                // 8 折
                return total.multiply(new BigDecimal("0.8"));

            default:
                throw new IllegalArgumentException("无效的优惠券码: " + couponCode);
        }
    }

    /**
     * 下单结账：计算总价 → 应用折扣 → 调用外部 PaymentService
     *
     * @param order 订单对象
     * @return 支付结果
     */
    public CheckoutResult checkout(Order order) {
        if (order == null || order.getProducts() == null || order.getProducts().isEmpty()) {
            return CheckoutResult.fail("订单为空");
        }

        BigDecimal total = calculateTotal(order.getProducts());
        BigDecimal finalPrice = applyDiscount(total, order.getCouponCode());

        try {
            String paymentId = paymentService.pay(order.getCustomerId(), finalPrice);
            return CheckoutResult.success(paymentId, finalPrice);
        } catch (Exception e) {
            return CheckoutResult.fail("支付失败: " + e.getMessage());
        }
    }

    // ============ 内部模型 ============

    public static class Product {
        private String name;
        private BigDecimal price;
        private int quantity;

        public Product() {}
        public Product(String name, BigDecimal price, int quantity) {
            this.name = name; this.price = price; this.quantity = quantity;
        }

        public String getName() { return name; }
        public BigDecimal getPrice() { return price; }
        public int getQuantity() { return quantity; }
    }

    public static class Order {
        private String customerId;
        private List<Product> products;
        private String couponCode;

        public Order() {}
        public Order(String customerId, List<Product> products, String couponCode) {
            this.customerId = customerId; this.products = products; this.couponCode = couponCode;
        }

        public String getCustomerId() { return customerId; }
        public List<Product> getProducts() { return products; }
        public String getCouponCode() { return couponCode; }
    }

    public static class CheckoutResult {
        private boolean success;
        private String paymentId;
        private BigDecimal finalPrice;
        private String error;

        public static CheckoutResult success(String paymentId, BigDecimal finalPrice) {
            CheckoutResult r = new CheckoutResult();
            r.success = true; r.paymentId = paymentId; r.finalPrice = finalPrice;
            return r;
        }
        public static CheckoutResult fail(String error) {
            CheckoutResult r = new CheckoutResult();
            r.success = false; r.error = error;
            return r;
        }

        public boolean isSuccess() { return success; }
        public String getPaymentId() { return paymentId; }
        public BigDecimal getFinalPrice() { return finalPrice; }
        public String getError() { return error; }
    }

    // ============ 外部依赖接口（方便 Mock） ============

    /**
     * PaymentService — 外部支付服务接口
     * 真实实现会调第三方支付网关，测试时用 Mockito Mock
     */
    public interface PaymentService {
        /**
         * 发起支付
         * @param customerId 客户 ID
         * @param amount     支付金额
         * @return 支付单号
         */
        String pay(String customerId, BigDecimal amount);
    }
}
