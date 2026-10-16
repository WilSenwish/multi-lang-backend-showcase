/** 场景 05：单元测试 — TS(Node) 实现（Vitest + sinon） */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import sinon from 'sinon';
import { OrderService, Product, Order, PaymentService } from '../src/order_service';

// ============ Fixture ============

function createMockPayment(): sinon.SinonStubbedInstance<PaymentService> {
  return {
    pay: sinon.stub().resolves('PAY-12345'),
  };
}

function createService(payment: sinon.SinonStubbedInstance<PaymentService>) {
  return new OrderService(payment);
}

// ============ calculateTotal ============

describe('calculateTotal', () => {
  it('正常计算多个产品', () => {
    const mock = createMockPayment();
    const svc = createService(mock);
    const products: Product[] = [
      { name: '苹果', price: 10, quantity: 2 },
      { name: '香蕉', price: 5, quantity: 3 },
    ];
    expect(svc.calculateTotal(products)).toBe(35);
  });

  it('空列表返回 0', () => {
    const mock = createMockPayment();
    const svc = createService(mock);
    expect(svc.calculateTotal([])).toBe(0);
  });

  it('null/undefined 返回 0', () => {
    const mock = createMockPayment();
    const svc = createService(mock);
    expect(svc.calculateTotal(null)).toBe(0);
    expect(svc.calculateTotal(undefined)).toBe(0);
  });
});

// ============ applyDiscount ============

describe('applyDiscount', () => {
  it('无优惠券返回原价', () => {
    const mock = createMockPayment();
    const svc = createService(mock);
    expect(svc.applyDiscount(100, null).price).toBe(100);
    expect(svc.applyDiscount(100, '').price).toBe(100);
    expect(svc.applyDiscount(100, undefined).price).toBe(100);
  });

  it('SAVE50 满100减50', () => {
    const mock = createMockPayment();
    const svc = createService(mock);
    expect(svc.applyDiscount(100, 'SAVE50').price).toBe(50);
    expect(svc.applyDiscount(80, 'SAVE50').price).toBe(80);
  });

  it('DISCOUNT10 九折', () => {
    const mock = createMockPayment();
    const svc = createService(mock);
    expect(svc.applyDiscount(100, 'DISCOUNT10').price).toBe(90);
  });

  it('DISCOUNT20 八折', () => {
    const mock = createMockPayment();
    const svc = createService(mock);
    expect(svc.applyDiscount(100, 'DISCOUNT20').price).toBe(80);
  });

  it('无效优惠券报错', () => {
    const mock = createMockPayment();
    const svc = createService(mock);
    const r = svc.applyDiscount(100, 'INVALID');
    expect(r.error).toBeDefined();
    expect(r.error!.includes('无效')).toBe(true);
  });
});

// ============ checkout（带 Mock） ============

describe('checkout', () => {
  it('支付成功返回 paymentId', async () => {
    const mock = createMockPayment();
    const svc = createService(mock);

    const order: Order = {
      customerId: 'customer-001',
      products: [{ name: '苹果', price: 10, quantity: 10 }],
      couponCode: 'DISCOUNT10',
    };

    const result = await svc.checkout(order);

    expect(result.success).toBe(true);
    expect(result.paymentId).toBe('PAY-12345');
    expect(result.finalPrice).toBe(90);
    sinon.assert.calledOnceWithExactly(mock.pay, 'customer-001', 90);
  });

  it('支付失败返回错误信息', async () => {
    const mock = createMockPayment();
    mock.pay.rejects(new Error('余额不足'));
    const svc = createService(mock);

    const order: Order = {
      customerId: 'customer-001',
      products: [{ name: '苹果', price: 10, quantity: 10 }],
    };

    const result = await svc.checkout(order);

    expect(result.success).toBe(false);
    expect(result.error!.includes('余额不足')).toBe(true);
  });

  it('空订单返回失败', async () => {
    const mock = createMockPayment();
    const svc = createService(mock);

    const order: Order = { customerId: 'customer-001', products: [] };
    const result = await svc.checkout(order);

    expect(result.success).toBe(false);
    sinon.assert.notCalled(mock.pay);
  });

  it('null 订单返回失败', async () => {
    const mock = createMockPayment();
    const svc = createService(mock);

    const result = await svc.checkout(null);
    expect(result.success).toBe(false);
  });
});
