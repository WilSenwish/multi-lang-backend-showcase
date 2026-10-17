package com.showcase.httpclient.service;

import java.util.Map;

/**
 * 外部调用最终失败（重试耗尽）时抛出，携带完整响应体。
 *
 * 为什么用异常而不是返回值：@CircuitBreaker（Resilience4j AOP）只在这两个
 * 时点记录熔断账 —— 方法正常返回记 success、抛异常记 failure。若在方法内把
 * 失败"咽下去"返回 failure map，熔断器永远看不到失败，三连失败也打不开。
 * 控制器捕获本异常后原样返回携带的 map。
 */
public class ExternalCallException extends RuntimeException {

    private final Map<String, Object> response;

    public ExternalCallException(Map<String, Object> response) {
        super("external call failed: " + response.get("error"));
        this.response = response;
    }

    public Map<String, Object> getResponse() {
        return response;
    }
}
