package com.showcase.streaming.dto;

/** 请求体（JSON 为 snake_case，由 spring.jackson.property-naming-strategy 统一转换）。 */
public record StreamRequest(Integer sizeMb, Integer chunkKib, Integer minAmount) {
}
