package com.showcase.ratelimit.controller;

import com.showcase.ratelimit.filter.TokenBucketRateLimiter;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.LinkedHashMap;
import java.util.Map;

@RestController
public class RateLimitController {

    private static final Logger log = LoggerFactory.getLogger(RateLimitController.class);

    @Autowired
    private TokenBucketRateLimiter limiter;

    private long totalRequests = 0;
    private long allowedRequests = 0;
    private long rejectedRequests = 0;

    /**
     * GET /api/heavy — 限流端点
     * 令牌桶通过 → 200，拒绝 → 429
     */
    @GetMapping("/api/heavy")
    public ResponseEntity<Object> heavy() {
        totalRequests++;

        if (!limiter.tryAcquire()) {
            rejectedRequests++;
            long retryAfterMs = limiter.retryAfterMs();

            Map<String, Object> resp = new LinkedHashMap<>();
            resp.put("error", "rate limit exceeded");
            resp.put("retry_after_ms", retryAfterMs);
            resp.put("total", totalRequests);
            resp.put("allowed", allowedRequests);
            resp.put("rejected", rejectedRequests);

            log.warn("[RateLimit] 429 被限流: retryAfter={}ms", retryAfterMs);

            return ResponseEntity.status(HttpStatus.TOO_MANY_REQUESTS)
                    .header("Retry-After", String.valueOf(Math.max(1, retryAfterMs / 1000)))
                    .body(resp);
        }

        allowedRequests++;
        log.info("[RateLimit] 200 通过");

        Map<String, Object> resp = new LinkedHashMap<>();
        resp.put("ok", true);
        resp.put("endpoint", "/api/heavy");
        resp.put("total", totalRequests);
        resp.put("allowed", allowedRequests);
        resp.put("rejected", rejectedRequests);

        return ResponseEntity.ok(resp);
    }

    /**
     * GET /health — 状态
     */
    @GetMapping("/health")
    public Map<String, Object> health() {
        Map<String, Object> resp = new LinkedHashMap<>();
        resp.put("service", "rate-limit-java");
        resp.put("algorithm", "token-bucket");
        resp.put("qps", limiter.getQps());
        resp.put("burst", limiter.getBurst());
        resp.put("total", totalRequests);
        resp.put("allowed", allowedRequests);
        resp.put("rejected", rejectedRequests);
        return resp;
    }
}
