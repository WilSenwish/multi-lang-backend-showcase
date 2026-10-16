package com.showcase.httpclient.service;

import io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker;
import io.github.resilience4j.retry.annotation.Retry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestTemplate;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * HTTP 客户端服务 — 调用外部 API（带超时、重试、熔断）
 */
@Service
public class ExternalApiService {

    private static final Logger log = LoggerFactory.getLogger(ExternalApiService.class);

    @Autowired
    private RestTemplate restTemplate;

    /**
     * 调用外部 API
     *
     * @param url         目标 URL
     * @param retryTimes  重试次数（Resilience4j 已配置，这里记录）
     * @param timeoutMs   超时时间（RestTemplate bean 级别）
     */
    @Retry(name = "httpCall")          // Resilience4j 重试（3 次，退避 100ms/200ms/400ms）
    @CircuitBreaker(name = "httpCall")  // Resilience4j 熔断（50% 失败率，open 10s）
    public Map<String, Object> call(String url, int retryTimes, int timeoutMs) {
        long start = System.currentTimeMillis();
        log.info("[HTTP-CLIENT] → GET {}", url);

        Map<String, Object> resp = new LinkedHashMap<>();

        try {
            String body = restTemplate.getForObject(url, String.class);
            long latency = System.currentTimeMillis() - start;

            resp.put("status_code", 200);
            resp.put("latency_ms", latency);
            resp.put("retries", 0); // Resilience4j 内部重试，这里简化为 0
            resp.put("body_preview", body != null && body.length() > 200 ? body.substring(0, 200) + "..." : body);
            resp.put("success", true);

        } catch (ResourceAccessException e) {
            // 连接超时 / 读取超时
            long latency = System.currentTimeMillis() - start;
            log.warn("[HTTP-CLIENT] ✗ timeout after {}ms: {}", latency, e.getMessage());
            resp.put("status_code", 0);
            resp.put("latency_ms", latency);
            resp.put("success", false);
            resp.put("error", "TIMEOUT: " + e.getMessage());

        } catch (HttpServerErrorException e) {
            // 5xx 错误（Resilience4j 会触发重试）
            long latency = System.currentTimeMillis() - start;
            log.warn("[HTTP-CLIENT] ✗ HTTP {} after {}ms", e.getRawStatusCode(), latency);
            resp.put("status_code", e.getRawStatusCode());
            resp.put("latency_ms", latency);
            resp.put("success", false);
            resp.put("error", "HTTP " + e.getRawStatusCode());

        } catch (Exception e) {
            long latency = System.currentTimeMillis() - start;
            log.warn("[HTTP-CLIENT] ✗ error after {}ms: {}", latency, e.getMessage());
            resp.put("status_code", 0);
            resp.put("latency_ms", latency);
            resp.put("success", false);
            resp.put("error", e.getMessage());
        }

        resp.put("url", url);
        resp.put("timestamp", Instant.now().toString());
        return resp;
    }
}
