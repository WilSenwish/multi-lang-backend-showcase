package com.showcase.httpclient.controller;

import com.showcase.httpclient.service.ExternalApiService;
import com.showcase.httpclient.service.ExternalCallException;
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.*;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

@RestController
public class HttpClientController {

    @Autowired
    private ExternalApiService externalApiService;

    @Autowired
    private CircuitBreakerRegistry circuitBreakerRegistry;

    @Value("${mock-server.port:8200}")
    private int mockPort;

    /**
     * POST /call-external — 调用外部 API
     *
     * 三种结局（响应键集合与其他四门语言逐字段一致）：
     *   成功      200 {status_code, latency_ms, retries, success, body_preview, url, timestamp}
     *   重试耗尽  200 {status_code, latency_ms, retries, success, error, url, timestamp}
     *   熔断中    200 {status_code:0, latency_ms:0, retries:0, success:false,
     *                  error:"CIRCUIT_OPEN: 熔断中", url, timestamp}
     */
    @PostMapping("/call-external")
    public Map<String, Object> callExternal(@RequestBody(required = false) Map<String, Object> body) {
        if (body == null) {
            body = Map.of();
        }
        String url = body.containsKey("url") && body.get("url") != null
                ? body.get("url").toString()
                : "http://localhost:" + mockPort + "/ok";
        int timeoutMs = body.containsKey("timeout_ms") && body.get("timeout_ms") != null
                ? ((Number) body.get("timeout_ms")).intValue()
                : 5000;
        int retryTimes = body.containsKey("retry_times") && body.get("retry_times") != null
                ? ((Number) body.get("retry_times")).intValue()
                : 2; // 总尝试次数 = retry_times + 1

        try {
            return externalApiService.call(url, retryTimes, timeoutMs);
        } catch (ExternalCallException e) {
            // 重试耗尽：服务已带上完整响应体（含 status_code / error），原样返回
            return e.getResponse();
        } catch (CallNotPermittedException e) {
            // 熔断器 OPEN：AOP 在方法调用前抛出，未产生任何 HTTP 尝试（latency=0）
            logCircuitOpen(url);
            Map<String, Object> resp = new LinkedHashMap<>();
            resp.put("status_code", 0);
            resp.put("latency_ms", 0);
            resp.put("retries", 0);
            resp.put("success", false);
            resp.put("error", "CIRCUIT_OPEN: 熔断中");
            resp.put("url", url);
            resp.put("timestamp", Instant.now().toString());
            return resp;
        }
    }

    private void logCircuitOpen(String url) {
        System.out.println("[HTTP-CLIENT] ✗ circuit open, request to " + url + " rejected");
    }

    /**
     * GET /health — 状态（含熔断器状态，与其他四门语言的 /health 字段一致）
     */
    @GetMapping("/health")
    public Map<String, Object> health() {
        // Resilience4j 的状态枚举是全大写（CLOSED/OPEN/HALF_OPEN），
        // 其他四门语言用小写 closed/open/half-open，这里统一转换。
        String raw = circuitBreakerRegistry.circuitBreaker("httpCall").getState().name();
        String state = "HALF_OPEN".equals(raw) ? "half-open" : raw.toLowerCase();
        Map<String, Object> resp = new LinkedHashMap<>();
        resp.put("service", "http-client-java");
        resp.put("mock_port", mockPort);
        resp.put("cb_state", state);
        return resp;
    }
}
