package com.showcase.concurrent.dto;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * 单个任务结果
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
public class TaskResult {
    private int id;
    private String status;
    private long durationMs;
}
