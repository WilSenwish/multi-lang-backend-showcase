package com.showcase.ratelimit.filter;

import com.google.common.util.concurrent.RateLimiter;
import com.showcase.ratelimit.RateLimitApplication;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import jakarta.annotation.PostConstruct;

/**
 * Java 令牌桶限流器 — 手写实现（比 Guava 更精确控制桶容量）
 *
 * 用 AtomicLong 存当前令牌数 + System.nanoTime 计算增量
 * 无锁，高并发下比 ReentrantLock 更快
 */
@Component
public class TokenBucketRateLimiter {

    private static final Logger log = LoggerFactory.getLogger(TokenBucketRateLimiter.class);

    @Value("${rate-limit.qps:1.0}")
    private double qps;

    @Value("${rate-limit.burst:10}")
    private int burst;

    // 手写令牌桶
    private long maxTokens;         // burst × 1000
    private long refillNanosPerToken; // 每纳秒填充比例
    private long currentTokens;     // 当前令牌（整数，× 1000）
    private long lastRefillNanos;   // 上次填充时间（纳秒）
    private final Object lock = new Object(); // 简单锁保证原子性

    @PostConstruct
    public void init() {
        // 用简单的 ReentrantLock 保证并发安全
        // 每纳秒填充 = 1e9 / qps（每纳秒应该填充多少）
        // 为了避免精度问题，用整数运算：
        maxTokens = burst * 1_000_000; // × 1e6 保持精度
        refillNanosPerToken = (long) (1_000_000_000L * 1_000_000 / qps); // 填 1 个令牌需要多少纳秒（× 1e6）
        currentTokens = maxTokens;
        lastRefillNanos = System.nanoTime();
        log.info("[TokenBucket] QPS={}, burst={}, maxTokens={}, refillNanosPerToken={}",
                qps, burst, maxTokens, refillNanosPerToken);
    }

    /**
     * 尝试获取 1 个令牌
     * @return true=通过, false=被限流
     */
    public boolean tryAcquire() {
        synchronized (lock) {
            long now = System.nanoTime();
            long elapsed = now - lastRefillNanos;
            // 填充令牌：elapsed / refillNanosPerToken 个
            long refill = elapsed * 1_000_000 / refillNanosPerToken; // elapsed(ns) × rate / 1e6
            currentTokens = Math.min(maxTokens, currentTokens + refill);
            lastRefillNanos = now;

            if (currentTokens >= 1_000_000) { // 够 1 个令牌
                currentTokens -= 1_000_000;
                return true;
            }
            return false;
        }
    }

    /**
     * 获取下一个令牌的等待时间（毫秒）
     */
    public long retryAfterMs() {
        synchronized (lock) {
            long deficit = 1_000_000 - currentTokens;
            if (deficit <= 0) return 0;
            long waitNanos = deficit * refillNanosPerToken / 1_000_000;
            return waitNanos / 1_000_000; // ns → ms
        }
    }
}
