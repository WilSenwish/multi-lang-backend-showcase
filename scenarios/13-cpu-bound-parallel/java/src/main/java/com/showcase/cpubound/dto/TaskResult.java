package com.showcase.cpubound.dto;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * 单个计算任务的结果 DTO
 *
 * <p>{@code checksum} 是**跨语言必须逐位一致**的字段：
 * 五门语言都按同一个 uint64 环绕算法计算，序列化为无符号十进制字符串。
 * JVM 的 long 是有符号的，所以这里用 {@code Long.toUnsignedString} 输出。
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
public class TaskResult {

    /** 任务序号，从 0 开始 */
    private int id;

    /** 该任务的计算结果（uint64 的无符号十进制表示） */
    private String checksum;

    /** 该任务耗时（毫秒），仅作参考，不参与跨语言断言 */
    private long durationMs;
}
