package com.showcase.errors.service;

import java.util.List;

/**
 * 应用错误：带 code、HTTP 状态与字段级 details。
 *
 * <p>Java 这边"错误类型"是**类型系统的一部分** —— 这是 checked exception 的双刃剑：
 * 调用方被迫处理（好事），但每一层都要重新声明或包装（样板），
 * 于是真实项目里大量出现"catch 掉然后包一层 RuntimeException"的机械代码。
 */
public class AppError extends RuntimeException {

    private final String code;
    private final int httpStatus;
    private final List<String> details;

    public AppError(String code, String message, int httpStatus, List<String> details, Throwable cause) {
        super(message, cause);
        this.code = code;
        this.httpStatus = httpStatus;
        this.details = details == null ? List.of() : List.copyOf(details);
    }

    public AppError(String code, String message, int httpStatus) {
        this(code, message, httpStatus, List.of(), null);
    }

    public AppError(String code, String message, int httpStatus, List<String> details) {
        this(code, message, httpStatus, details, null);
    }

    public String code() {
        return code;
    }

    public int httpStatus() {
        return httpStatus;
    }

    public List<String> details() {
        return details;
    }
}
