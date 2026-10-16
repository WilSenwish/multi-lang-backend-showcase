package com.showcase.ratelimit.filter;

import com.google.common.util.concurrent.RateLimiter;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import jakarta.annotation.PostConstruct;

/**
 * Java 令牌桶限流器 — Guava RateLimiter
 *
 * 并发安全：RateLimiter 内部用 StampedLock + 原子变量
 * 实现令牌桶算法。
 *
 * Guava RateLimiter.create(permitsPerSecond) 有 warmup 特性：
 * - RateLimiter.create(qps) 匀速填充（稳定后）
 * - RateLimiter.create(qps, warmupPeriod, unit) 预热期（逐渐加速到稳定速率）
 */
@Component
public class RateLimiterWrapper {

    @Value("${rate-limit.qps:1.0}")
    private double qps;

    @Value("${rate-limit.burst:10}")
    private int burst;

    private RateLimiter limiter;

    @PostConstruct
    public void init() {
        // 每秒 qps 个令牌
        // burst 控制桶容量：acquire(burst) 一次最多拿 burst 个
        this.limiter = RateLimiter.create(qps);
        // Guava RateLimiter 的桶容量由 double permits 参数决定，
        // 实际是 limiter 的"最大允许突发量" = 1（qps）+ max(0, burst - 1)
        // 为了精确控制，我们手动创建一个容量 burst 的令牌桶：
        // RateLimiter 没有直接设桶容量的 API，用 acquire 控制每次消费 1 个即可
        // 桶容量 ≈ qps 的倍数：10 QPS 的桶容量大概是 burst
        // 这里简化：每次请求 acquire(1)，如果 rateLimiter 拒绝则 429
        System.out.println("[RateLimiter] QPS=" + qps + ", burst=" + burst + " (每次请求消耗 1 个令牌)");
    }

    /**
     * 尝试获取令牌
     * @return 是否通过限流
     */
    public boolean tryAcquire() {
        return limiter.tryAcquire(); // 零等待，拿不到立即返回 false
    }

    /**
     * 获取等待时间（毫秒）
     *
     * 说明：Guava 的 RateLimiter.reserve(int) 为包级私有，未对外暴露，
     * 这里基于公开的 getRate() 估算下一个令牌的等待时间（非阻塞）。
     */
    public long reserve() {
        double rate = limiter.getRate();
        return rate <= 0 ? 0L : (long) (1000.0 / rate);
    }
}
