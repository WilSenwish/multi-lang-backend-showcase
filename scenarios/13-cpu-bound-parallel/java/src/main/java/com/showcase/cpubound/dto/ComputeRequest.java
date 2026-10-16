package com.showcase.cpubound.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * 计算请求 DTO
 *
 * <p>字段命名与其余四门语言的 JSON 契约保持一致（snake_case），
 * 依赖 application.properties 中的 {@code spring.jackson.property-naming-strategy=SNAKE_CASE} 完成转换。
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class ComputeRequest {

    /** 任务总数，默认 8 */
    private Integer taskCount;

    /** 单个任务的迭代次数，默认 2_000_000（决定单任务耗时量级） */
    private Long iterations;

    /** 同时执行的任务数上限，默认 4 —— 与场景 02 同语义，保证对比公平 */
    private Integer concurrency;
}
