package com.showcase.logging.controller;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.web.bind.annotation.*;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

/**
 * 场景 07：结构化日志 — Java 实现
 *
 * Java 结构化日志特点：
 * 1. SLF4J API + Logback 实现 + logstash-logback-encoder 输出 JSON
 * 2. MDC（Mapped Diagnostic Context）是 Java 独有特性，放 requestId 等链路字段
 * 3. logback-spring.xml 配置 JSON encoder，一次性配置全生效
 * 4. 支持 caller 信息（类名、方法、行号）嵌入 JSON
 *
 * 对比其他语言：
 * - Java 通过 MDC 自动给所有日志加 requestId（Go 要手动传 context）
 * - Logback JSON encoder 支持自定义字段、错误栈、caller
 * - 但依赖多（Logback + logstash-logback-encoder ≈ 3MB），配置啰嗦
 */
@RestController
public class LoggingController {

    private static final Logger log = LoggerFactory.getLogger(LoggingController.class);

    /**
     * GET /ping — 简单请求 + INFO 级别日志
     */
    @GetMapping("/ping")
    public Map<String, Object> ping() {
        long start = System.currentTimeMillis();
        String requestId = UUID.randomUUID().toString().substring(0, 8);

        // MDC 放链路追踪字段，后续所有日志自动带上
        MDC.put("requestId", requestId);
        MDC.put("userId", "anonymous");
        MDC.put("path", "/ping");

        try {
            log.info("ping request handled");

            Map<String, Object> resp = new LinkedHashMap<>();
            resp.put("pong", true);
            resp.put("request_id", requestId);
            return resp;
        } finally {
            long cost = System.currentTimeMillis() - start;
            // 带结构化字段的 INFO 日志
            log.info("request completed",
                    "costMs", cost,
                    "endpoint", "/ping");
            MDC.clear();
        }
    }

    /**
     * GET /debug — DEBUG 级别日志（生产默认不开）
     */
    @GetMapping("/debug")
    public Map<String, Object> debug() {
        String requestId = UUID.randomUUID().toString().substring(0, 8);
        MDC.put("requestId", requestId);
        MDC.put("userId", "debug-user");

        try {
            // 只有 DEBUG 级别开启时才会输出
            log.debug("debug request received", "param1", "value1", "param2", 42);
            log.info("debug endpoint hit");

            return Map.of("debug", true, "request_id", requestId);
        } finally {
            MDC.clear();
        }
    }

    /**
     * GET /error — 故意触发异常 + ERROR 级别日志（带错误栈）
     */
    @GetMapping("/error")
    public Map<String, Object> error() {
        String requestId = UUID.randomUUID().toString().substring(0, 8);
        MDC.put("requestId", requestId);
        MDC.put("userId", "error-user");

        try {
            // 故意触发 NPE
            String nullStr = null;
            nullStr.length(); // NPE!
        } catch (Exception e) {
            // ERROR 级别日志，Logback 会把整个异常栈嵌入 JSON 的 stack_trace 字段
            log.error("request failed with exception",
                    "costMs", 150,
                    "errorCode", "NULL_POINTER",
                    e); // 最后一个 Throwable 参数自动被识别为异常
        } finally {
            MDC.clear();
        }

        return Map.of("error", "simulated");
    }

    /**
     * GET /bench?count=1000 — 性能测试：连续打 N 条日志
     */
    @GetMapping("/bench")
    public Map<String, Object> bench(@RequestParam(defaultValue = "1000") int count) {
        String requestId = UUID.randomUUID().toString().substring(0, 8);
        MDC.put("requestId", requestId);

        long start = System.currentTimeMillis();
        for (int i = 0; i < count; i++) {
            log.info("benchmark log entry",
                    "index", i,
                    "total", count);
        }
        long cost = System.currentTimeMillis() - start;

        MDC.clear();

        log.info("benchmark completed",
                "count", count,
                "totalCostMs", cost,
                "avgLogNs", count > 0 ? (cost * 1_000_000L / count) : 0);

        Map<String, Object> resp = new LinkedHashMap<>();
        resp.put("count", count);
        resp.put("total_cost_ms", cost);
        resp.put("avg_log_ns", count > 0 ? (cost * 1_000_000L / count) : 0);
        resp.put("request_id", requestId);
        return resp;
    }
}
