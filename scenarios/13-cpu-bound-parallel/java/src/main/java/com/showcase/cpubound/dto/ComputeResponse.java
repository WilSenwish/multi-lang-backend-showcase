package com.showcase.cpubound.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;

/**
 * 计算响应 DTO
 *
 * <p>其中 {@code checksum}、{@code totalTasks}、{@code iterations}、{@code concurrency}
 * 与 {@code results} 属于**契约字段**，五门语言必须完全一致（见 VERIFICATION.md 的契约级断言）；
 * {@code totalTimeMs} / {@code cpuCores} / {@code durationMs} 属于**环境相关字段**，仅作参考。
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class ComputeResponse {

    /** 实际执行的任务数 */
    private int totalTasks;

    /** 单任务迭代次数（回显） */
    private long iterations;

    /** 实际生效的并发上限（回显） */
    private int concurrency;

    /** 运行时可见的 CPU 核心数 */
    private int cpuCores;

    /** 总耗时（毫秒） */
    private long totalTimeMs;

    /** 全部任务结果的 uint64 累加和（模 2^64），无符号十进制字符串 */
    private String checksum;

    /** 逐任务结果，按 id 升序 */
    private List<TaskResult> results;
}
