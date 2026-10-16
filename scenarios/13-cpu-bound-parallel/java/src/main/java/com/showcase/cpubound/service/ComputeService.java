package com.showcase.cpubound.service;

import com.showcase.cpubound.dto.ComputeRequest;
import com.showcase.cpubound.dto.ComputeResponse;
import com.showcase.cpubound.dto.TaskResult;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

/**
 * 场景 13：CPU 密集并行计算 — 业务实现
 *
 * <h3>为什么单独做一个 CPU 密集场景？</h3>
 * 场景 02 的任务是 {@code sleep}（IO 密集），瓶颈在等待而不在 CPU，
 * 因此 Python 的 GIL、Node 的单线程事件循环都不会暴露 —— 五门语言耗时接近。
 * 把任务换成纯计算后，差距会被直接量化：
 * <ul>
 *   <li>Java：平台线程真并行，{@code -Xmx} 不变，纯吃 CPU</li>
 *   <li>Go：goroutine + GOMAXPROCS，真并行</li>
 *   <li>Rust：std::thread，真并行且无 GC 干扰</li>
 *   <li>Python：**GIL 使多线程无法并行计算**，必须上 multiprocessing</li>
 *   <li>TS(Node)：**单线程**，必须上 worker_threads</li>
 * </ul>
 *
 * <h3>算法为什么用 uint64 环绕的 LCG？</h3>
 * <ul>
 *   <li>纯整数运算 → 无浮点误差，五门语言结果可以**逐位比对**；</li>
 *   <li>固定的乘加循环 → 编译器无法优化掉，能真实压满 CPU；</li>
 *   <li>要求 64 位无符号环绕 → 顺带暴露"TS 没有 64 位整数，必须用 BigInt"这个本质差异。</li>
 * </ul>
 */
@Service
public class ComputeService {

    /** MMIX 线性同余发生器常数：state = state * MULT + INC (mod 2^64) */
    private static final long MULT = 6364136223846793005L;
    private static final long INC = 1442695040888963407L;

    private static final int DEFAULT_TASK_COUNT = 8;
    private static final long DEFAULT_ITERATIONS = 2_000_000L;
    private static final int DEFAULT_CONCURRENCY = 4;

    /**
     * 执行 CPU 密集的并行计算
     *
     * @param req 请求参数（允许缺省，缺省值见常量）
     * @return 计算结果，checksum 为全部任务结果的 uint64 累加和
     */
    public ComputeResponse run(ComputeRequest req) {
        int taskCount = clamp(req.getTaskCount(), DEFAULT_TASK_COUNT);
        long iterations = clamp(req.getIterations(), DEFAULT_ITERATIONS);
        int concurrency = Math.min(clamp(req.getConcurrency(), DEFAULT_CONCURRENCY), taskCount);

        long startNs = System.nanoTime();

        // 固定大小线程池 = 并发上限本身。
        // 注意：这里控制的是"同时运行的计算任务数"，而不是"CPU 核心数"。
        // 若 concurrency > 核心数，线程会互相抢占 CPU，总耗时不再随并发线性下降 ——
        // 这正是 CPU 密集与 IO 密集最大的行为差异，也是本场景要展示的点。
        ExecutorService executor = Executors.newFixedThreadPool(concurrency);
        try {
            List<Future<TaskResult>> futures = new ArrayList<>(taskCount);
            for (int i = 0; i < taskCount; i++) {
                final int taskId = i;
                futures.add(executor.submit(() -> computeTask(taskId, iterations)));
            }

            List<TaskResult> results = new ArrayList<>(taskCount);
            long checksum = 0L;
            for (Future<TaskResult> f : futures) {
                // get() 会等待该任务完成；这里不需要额外超时控制，因为任务是纯计算、必定完成
                TaskResult r = f.get();
                results.add(r);
                checksum += Long.parseUnsignedLong(r.getChecksum());
            }

            long elapsedMs = TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - startNs);

            return ComputeResponse.builder()
                    .totalTasks(taskCount)
                    .iterations(iterations)
                    .concurrency(concurrency)
                    .cpuCores(Runtime.getRuntime().availableProcessors())
                    .totalTimeMs(elapsedMs)
                    .checksum(Long.toUnsignedString(checksum))
                    .results(results)
                    .build();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("计算被中断", e);
        } catch (Exception e) {
            throw new IllegalStateException("计算失败", e);
        } finally {
            executor.shutdown();
        }
    }

    /**
     * 单个计算任务：对 id 派生的种子跑 iterations 次 LCG 迭代。
     *
     * <p>JVM 的 {@code long} 是有符号的，但乘加溢出在补码下与 uint64 环绕**位模式完全等价**，
     * 因此无需任何无符号类型即可得到与 Go/Rust 一致的结果；只有**输出**时才需要
     * {@link Long#toUnsignedString} 把位模式解释成无符号十进制。
     */
    private TaskResult computeTask(int id, long iterations) {
        long taskStartNs = System.nanoTime();
        long state = id + 1L;
        for (long i = 0; i < iterations; i++) {
            state = state * MULT + INC;
        }
        long durationMs = TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - taskStartNs);
        return new TaskResult(id, Long.toUnsignedString(state), durationMs);
    }

    /** 缺省值填充 + 下界保护 */
    private static int clamp(Integer v, int fallback) {
        return (v == null || v < 1) ? fallback : v;
    }

    private static long clamp(Long v, long fallback) {
        return (v == null || v < 1) ? fallback : v;
    }
}
