package com.showcase.errors.dto;

import java.util.List;

/**
 * 统一的结构化错误响应体（五门语言逐字段一致）。
 *
 * <p>{@code trace_id} 回显请求头 {@code X-Trace-Id} —— 错误路径上有没有把上下文带出来，
 * 是"深水区"的第一个可断言事实。
 */
public record ErrorBody(
        String kind,
        String code,
        String message,
        String traceId,
        List<String> causeChain,
        List<String> details,
        boolean stackPresent,
        boolean recovered
) {}
