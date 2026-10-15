package com.showcase.concurrent.dto;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * 请求 DTO
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
public class RunRequest {
    /** 任务总数 */
    private int taskCount = 100;
    /** 每个任务模拟耗时（毫秒） */
    private int taskDelayMs = 100;
    /** 同时最多执行的任务数 */
    private int concurrency = 10;
}
