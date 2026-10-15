package com.showcase.concurrent.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;

/**
 * 响应 DTO
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class RunResponse {
    private int totalTasks;
    private int concurrency;
    private long totalTimeMs;
    private double throughput;
    private int taskDelayMs;
    private List<TaskResult> results;
}
