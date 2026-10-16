package com.showcase.errors.dto;

/** 错误观测面板：区分"进了处理器的错误"与"脱离请求上下文的异步错误"。 */
public record StatsBody(
        int handled,
        int unhandled,
        int panicsRecovered,
        String lastUnhandled,
        String lastTraceId
) {}
