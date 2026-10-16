/**
 * 场景 05：单元测试 & Mock — TS(Node) 实现（Vitest + sinon）
 *
 * Node 测试框架特点：
 * 1. Vitest（Jest 的超集，速度更快，Vite 生态）
 * 2. sinon 做 Mock/stub/spy（最流行的测试工具库）
 * 3. 也可以用 Jest 内置 jest.fn()，但 sinon 更灵活
 * 4. c8 生成覆盖率报告
 * 5. Vitest 原生支持 TS，无需编译直接测
 *
 * 和 Java/Python/Rust 对比：
 * - Jest/Vitest 生态最大（npm 上百万包）
 * - Mock 方式极灵活：mock 任何函数、类、全局对象
 * - 但 TS 类型只是编译期，运行时 Mock 不受类型约束
 */

// ============ 业务模型 ============

export interface Product {
  name: string;
  price: number;
  quantity: number;
}

export interface Order {
  customerId: string;
  products: Product[];
  couponCode?: string | null;
}

export interface CheckoutResult {
  success: boolean;
  paymentId?: string;
  finalPrice: number;
  error?: string;
}

// ============ 外部依赖接口（方便 Mock） ============

export interface PaymentService {
  pay(customerId: string, amount: number): Promise<string>;
}

// ============ 业务类 ============

export class OrderService {
  constructor(private payment: PaymentService) {}

  /** 计算订单总价 */
  calculateTotal(products: Product[] | null | undefined): number {
    if (!products || products.length === 0) return 0;
    return products.reduce((sum, p) => sum + p.price * p.quantity, 0);
  }

  /** 应用优惠券折扣 */
  applyDiscount(total: number, couponCode?: string | null): { price: number; error?: string } {
    if (total <= 0) return { price: 0 };
    if (!couponCode) return { price: total };

    const coupon = couponCode.toUpperCase();
    switch (coupon) {
      case 'SAVE50':
        return { price: total >= 100 ? total - 50 : total };
      case 'DISCOUNT10':
        return { price: total * 0.9 };
      case 'DISCOUNT20':
        return { price: total * 0.8 };
      default:
        return { price: 0, error: `无效的优惠券码: ${couponCode}` };
    }
  }

  /** 下单结账 */
  async checkout(order: Order | null | undefined): Promise<CheckoutResult> {
    if (!order || order.products.length === 0) {
      return { success: false, finalPrice: 0, error: '订单为空' };
    }

    const total = this.calculateTotal(order.products);
    const { price: finalPrice, error } = this.applyDiscount(total, order.couponCode);
    if (error) {
      return { success: false, finalPrice: 0, error };
    }

    try {
      const paymentId = await this.payment.pay(order.customerId, finalPrice);
      return { success: true, paymentId, finalPrice };
    } catch (e: any) {
      return { success: false, finalPrice, error: `支付失败: ${e.message}` };
    }
  }
}
