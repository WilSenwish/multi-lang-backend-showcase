package com.showcase.concurrent.controller;

import com.showcase.concurrent.dto.RunRequest;
import com.showcase.concurrent.dto.RunResponse;
import com.showcase.concurrent.dto.TaskResult;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.*;
import java.util.stream.Collectors;

/**
 * 场景 02：并发任务处理控制器
 *
 * 核心实现：
 * - 使用固定线程池（大小 = 请求的 concurrency）控制并发上限
 * - CompletableFuture.supplyAsync 提交任务
 * - CompletableFuture.allOf 等待全部完成
 *
 * 这是 Java 生态中控制并发数的经典做法：
 * Executors.newFixedThreadPool(concurrency) 本身就保证了同时最多 concurrency 个线程在执行
 */
@RestController
public class ConcurrentTaskController {

    /**
     * 执行并发任务
     *
     * Java 并发模型特点：
     * 1. 每个平台线程约 1MB 栈内存，不能无限制创建
     * 2. ThreadPoolExecutor 是控制并发上限的核心手段
     * 3. CompletableFuture 提供异步链式编排能力
     * 4. 这里的 sleep 是 Thread.sleep，会阻塞线程
     */
    @PostMapping("/run")
    public RunResponse run(@RequestBody RunRequest req) {
        // 统一契约：字段缺省走 DTO 默认值（100/100/10），显式传入非法值一律 400
        // —— 与 Go/Python/Rust/TS 的校验行为对齐，不再静默夹取
        if (req.getTaskCount() < 1) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "task_count must be >= 1");
        }
        if (req.getTaskDelayMs() < 0) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "task_delay_ms must be >= 0");
        }
        if (req.getConcurrency() < 1) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "concurrency must be >= 1");
        }

        long startNs = System.nanoTime();

        // 边界保护：并发数不超过任务数（这是契约行为，其余四门同样如此）
        int taskCount = req.getTaskCount();
        int delayMs = req.getTaskDelayMs();
        int concurrency = Math.min(req.getConcurrency(), taskCount);

        // 创建固定大小线程池 — 这就是 Java 版的 "并发限流原语"
        // 同时最多 concurrency 个任务在执行，超出的任务在线程池队列里等待
        ExecutorService executor = Executors.newFixedThreadPool(concurrency);
        try {
            // 提交 taskCount 个异步任务到线程池
            List<CompletableFuture<TaskResult>> futures = new ArrayList<>();
            for (int i = 0; i < taskCount; i++) {
                final int taskId = i;
                futures.add(CompletableFuture.supplyAsync(() -> executeTask(taskId, delayMs), executor));
            }

            // 等待全部完成
            CompletableFuture.allOf(futures.toArray(new CompletableFuture[0])).join();

            // 收集结果（保持顺序）
            List<TaskResult> results = futures.stream()
                    .map(CompletableFuture::join)
                    .collect(Collectors.toList());

            long elapsedMs = TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - startNs);
            double throughput = (elapsedMs > 0) ? (taskCount * 1000.0 / elapsedMs) : taskCount;

            return RunResponse.builder()
                    .totalTasks(taskCount)
                    .concurrency(concurrency)
                    .totalTimeMs(elapsedMs)
                    .throughput(Math.round(throughput * 100) / 100.0)
                    .taskDelayMs(delayMs)
                    .results(results)
                    .build();
        } finally {
            // 关闭线程池（Spring 没有自动管理它，因为是运行时动态创建的）
            executor.shutdown();
        }
    }

    /**
     * 单个任务：sleep 指定毫秒后返回结果
     * 模拟 IO 密集操作（如调用外部 HTTP 接口）
     */
    private TaskResult executeTask(int id, int delayMs) {
        long taskStartNs = System.nanoTime();
        try {
            Thread.sleep(delayMs);
            long durationMs = TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - taskStartNs);
            return new TaskResult(id, "ok", durationMs);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            long durationMs = TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - taskStartNs);
            return new TaskResult(id, "error", durationMs);
        }
    }
}
