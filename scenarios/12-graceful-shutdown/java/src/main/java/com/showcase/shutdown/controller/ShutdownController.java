package com.showcase.shutdown.controller;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * 优雅关闭 Demo Controller
 *
 * 关键设计：
 * 1. long-task 模拟耗时请求（2-5s）
 * 2. shutdown 期间仍在处理的 long-task 会被等待
 * 3. 用 AtomicInteger 追踪正在处理的请求数
 */
@RestController
public class ShutdownController {

    private static final Logger log = LoggerFactory.getLogger(ShutdownController.class);

    private final AtomicInteger inFlightRequests = new AtomicInteger(0);
    private volatile boolean shuttingDown = false;

    // 提供给 ShutdownConfig 读取
    public int getInFlightCount() { return inFlightRequests.get(); }
    public boolean isShuttingDown() { return shuttingDown; }
    public void markShuttingDown() { this.shuttingDown = true; }

    /**
     * GET /api/long-task — 模拟耗时 3s 的请求
     * 发送 SIGTERM 后，正在处理的这个请求应该被等待完成
     */
    @GetMapping("/api/long-task")
    public Map<String, Object> longTask() throws InterruptedException {
        int id = inFlightRequests.incrementAndGet();
        log.info("[REQUEST] 开始处理 long-task, id={}, in-flight={}", id, inFlightRequests.get());

        try {
            // 模拟 3s 耗时
            Thread.sleep(3000);
            log.info("[REQUEST] 完成 long-task, id={}", id);
        } finally {
            inFlightRequests.decrementAndGet();
        }

        return Map.of(
                "ok", true,
                "duration_ms", 3000,
                "shutting_down", shuttingDown
        );
    }

    /**
     * GET /api/health — readiness probe
     * K8s 中关闭期间返回非 200，让探针标记 pod 不 ready
     */
    @GetMapping("/api/health")
    public ResponseEntity<Map<String, Object>> health() {
        Map<String, Object> body = Map.of(
                "service", "graceful-shutdown-java",
                "shutting_down", shuttingDown,
                "in_flight", inFlightRequests.get()
        );

        if (shuttingDown) {
            return ResponseEntity.status(503).body(body); // Service Unavailable
        }
        return ResponseEntity.ok(body);
    }
}
