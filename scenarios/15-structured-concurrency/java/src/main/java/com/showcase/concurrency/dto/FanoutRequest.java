package com.showcase.concurrency.dto;

/**
 * 扇出请求（JSON 为 snake_case，由全局命名策略转换）。
 * 缺省值由 Service 补齐：tasks=6 / task_ms=300 / fail_index=-1 / fail_after_ms=100 / timeout_ms=0。
 */
public record FanoutRequest(
        Integer tasks,
        Integer taskMs,
        Integer failIndex,
        Integer failAfterMs,
        Integer timeoutMs
) {
}
