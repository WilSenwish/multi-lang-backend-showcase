package com.showcase.httpclient.service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.showcase.httpclient.config.HttpClientConfig;
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.CloseableHttpResponse;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManager;
import org.apache.hc.core5.http.ClassicHttpRequest;
import org.apache.hc.core5.http.HttpEntity;
import org.apache.hc.core5.http.io.entity.EntityUtils;
import org.apache.hc.core5.http.message.BasicClassicHttpRequest;
import org.apache.hc.core5.http.Method;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.function.Supplier;

/**
 * HTTP 客户端服务 — 调用外部 API（带超时、重试、熔断）
 *
 * 与其他四门语言对齐的统一契约：
 * - 重试：服务内手工指数退避（100ms → 200ms → 400ms），次数取请求体的 retry_times。
 *   老代码用 @Retry 注解驱动，max-attempts 固定 3、退避固定 500ms，
 *   请求体里的 retry_times 被整个忽略（API 收了参数却不生效）。
 * - 超时：逐请求 RequestConfig（connect 3s / response timeout_ms）。
 *   老代码的 RestTemplate bean 固定 3s/10s，timeout_ms 同样被忽略。
 * - 熔断：Resilience4j CircuitBreaker，**编程式**调用（executeSupplier）。
 *   为什么不用 @CircuitBreaker 注解：resilience4j-spring-boot3 2.x 只自动注册
 *   Registry，不自动注册 Aspect；手动 @Import(CircuitBreakerConfiguration.class)
 *   又会与自动配置的 registry bean 撞定义。编程式用法语义完全等价
 *   （executeSupplier 在方法抛异常时记 failure、OPEN 时抛 CallNotPermittedException），
 *   且不依赖 Aspect 的注册方式。
 *
 * 响应键集合（跨语言统一）：
 *   成功      {status_code, latency_ms, retries, success, body_preview, url, timestamp}
 *   重试耗尽  {status_code, latency_ms, retries, success, error, url, timestamp}
 *   熔断中    {status_code:0, latency_ms:0, retries:0, success:false, error:"CIRCUIT_OPEN: 熔断中", url, timestamp}
 */
@Service
public class ExternalApiService {

    private static final Logger log = LoggerFactory.getLogger(ExternalApiService.class);

    private static final ObjectMapper MAPPER = new ObjectMapper();

    @Autowired
    private CircuitBreakerRegistry circuitBreakerRegistry;

    @Autowired
    private PoolingHttpClientConnectionManager connectionManager;

    /**
     * 调用外部 API
     *
     * @param url         目标 URL
     * @param retryTimes  重试次数（不含首次，总共最多 retryTimes + 1 次）
     * @param timeoutMs   单次尝试的读取超时（毫秒）
     * @throws ExternalCallException  重试耗尽（携带完整响应 map，熔断器记一次失败）
     * @throws CallNotPermittedException 熔断器 OPEN（未产生任何 HTTP 尝试）
     */
    public Map<String, Object> call(String url, int retryTimes, int timeoutMs) {
        CircuitBreaker cb = circuitBreakerRegistry.circuitBreaker("httpCall");
        try {
            // executeSupplier： supplier 抛异常 → 记一次失败并原样抛出；
            // 熔断器 OPEN → 直接抛 CallNotPermittedException，不进 supplier。
            return cb.executeSupplier((Supplier<Map<String, Object>>)
                    () -> callWithRetry(url, retryTimes, timeoutMs));
        } catch (CallNotPermittedException e) {
            throw e; // 上抛给控制器，转换为 CIRCUIT_OPEN 响应
        }
    }

    private Map<String, Object> callWithRetry(String url, int retryTimes, int timeoutMs) {
        long start = System.currentTimeMillis();
        String lastError = null;
        int lastStatus = 0; // 最后一次尝试拿到的 HTTP 状态码（网络错误时为 0）

        for (int attempt = 0; attempt <= retryTimes; attempt++) {
            if (attempt > 0) {
                // 指数退避：100ms → 200ms → 400ms（与其他四门语言一致）
                long backoffMs = (long) (100 * Math.pow(2, attempt - 1));
                try {
                    Thread.sleep(backoffMs);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    break;
                }
            }

            log.info("[HTTP-CLIENT] → GET {} (attempt {})", url, attempt + 1);

            int status;
            String body;
            try (CloseableHttpClient client = HttpClientConfig.buildClient(connectionManager, timeoutMs)) {
                ClassicHttpRequest request = new BasicClassicHttpRequest(Method.GET, url);
                try (CloseableHttpResponse resp = client.execute(request)) {
                    status = resp.getCode();
                    HttpEntity entity = resp.getEntity();
                    body = entity != null ? EntityUtils.toString(entity, StandardCharsets.UTF_8) : null;
                }
            } catch (Exception e) {
                // 连接失败 / 读超时
                lastError = "REQUEST_ERROR: " + e.getMessage();
                lastStatus = 0;
                log.warn("[HTTP-CLIENT] ✗ error after {}ms: {}", System.currentTimeMillis() - start, e.getMessage());
                continue;
            }

            lastStatus = status;

            // 5xx 重试；最后一次也失败时按"重试耗尽"语义返回真实状态码
            // （README 统一接口：重试 2 次后 status_code=500）
            if (status >= 500) {
                lastError = "HTTP " + status;
                log.warn("[HTTP-CLIENT] ✗ HTTP {} after {}ms", status, System.currentTimeMillis() - start);
                if (attempt < retryTimes) {
                    continue;
                }
                break;
            }

            // 成功（< 500）：body_preview 解析为 JSON 对象（与其他四门语言一致，
            // 老代码 getForObject(url, String.class) 拿到的是原始字符串）
            Map<String, Object> resp = baseResp(url, start);
            resp.put("status_code", status);
            resp.put("latency_ms", System.currentTimeMillis() - start);
            resp.put("retries", attempt);
            resp.put("success", status < 400);
            resp.put("body_preview", parseBody(body));
            return resp;
        }

        // 重试耗尽：抛异常让熔断器记录一次失败，控制器原样返回响应体
        Map<String, Object> resp = baseResp(url, start);
        resp.put("status_code", lastStatus);
        resp.put("latency_ms", System.currentTimeMillis() - start);
        resp.put("retries", retryTimes);
        resp.put("success", false);
        resp.put("error", lastError != null ? lastError : "unknown error");
        throw new ExternalCallException(resp);
    }

    private Map<String, Object> baseResp(String url, long start) {
        Map<String, Object> resp = new LinkedHashMap<>();
        resp.put("url", url);
        resp.put("timestamp", Instant.now().toString());
        return resp;
    }

    private Object parseBody(String body) {
        if (body == null || body.isEmpty()) {
            return null;
        }
        try {
            return MAPPER.readValue(body, new TypeReference<Map<String, Object>>() {});
        } catch (Exception e) {
            // 非 JSON 响应体：退化为字符串（截断 200 字符），与其他语言行为一致
            return body.length() > 200 ? body.substring(0, 200) : body;
        }
    }
}
