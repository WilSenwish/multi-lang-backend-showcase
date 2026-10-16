package com.showcase.concurrency.service;

import com.showcase.concurrency.dto.FanoutRequest;
import com.showcase.concurrency.dto.FanoutResponse;
import com.showcase.concurrency.dto.StatsResponse;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.StructuredTaskScope;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

/**
 * 扇出聚合：一个作用域内并发跑 N 个子任务，任一失败或父作用域超时则取消全部兄弟任务。
 *
 * <p><b>Java 侧的关键事实（2026-10-16 实测，见场景 README 的对照实验）</b>：
 * {@code StructuredTaskScope} <b>没有显式的取消信号</b>——{@code shutdown()} / {@code close()}
 * 不会像 Go 的 {@code context}、Python 的 {@code CancelledError}、Node 的 {@code AbortSignal}
 * 那样"传播一个值"，而是直接<b>中断</b>未完成的子任务线程（{@code Thread.interrupt()}）。
 * 因此在本用例（阻塞点是 {@code Thread.sleep}）里，即使完全不手写取消标志，
 * 兄弟任务也会被中断而提前退出（实测 elapsed 仍约 260ms）。
 *
 * <p>这是便利，也是代价：中断<b>只对可中断的阻塞点生效</b>，遇到不可中断的忙循环或
 * 某些阻塞 IO 就失效，且中断不携带"为什么被取消"的信息。
 * 所以本实现同时保留一条手写兜底路径：{@link AtomicBoolean} 取消标志 + 等待循环每 5ms 检查，
 * 并把中断统一归一化成 {@code cancelled}（与其余四门语言的字段语义一致）。
 */
@Service
public class FanoutService {

    private static final int POLL_MS = 5;

    private final AtomicLong active = new AtomicLong();
    private final AtomicLong started = new AtomicLong();
    private final AtomicLong completed = new AtomicLong();
    private final AtomicLong cancelled = new AtomicLong();
    private final AtomicLong failed = new AtomicLong();

    public StatsResponse stats() {
        return new StatsResponse("java", active.get(), started.get(),
                completed.get(), cancelled.get(), failed.get());
    }

    public FanoutResponse fanout(FanoutRequest req) {
        int tasks = req.tasks() == null ? 6 : req.tasks();
        int taskMs = req.taskMs() == null ? 300 : req.taskMs();
        int failIndex = req.failIndex() == null ? -1 : req.failIndex();
        int failAfterMs = req.failAfterMs() == null ? 100 : req.failAfterMs();
        int timeoutMs = req.timeoutMs() == null ? 0 : req.timeoutMs();

        long t0 = System.currentTimeMillis();
        String[] outcomes = new String[tasks];
        // ⭐ 手写取消标志：StructuredTaskScope 不会替你传播取消
        AtomicBoolean cancel = new AtomicBoolean(false);
        boolean[] timedOut = {false};

        try (StructuredTaskScope.ShutdownOnFailure scope = new StructuredTaskScope.ShutdownOnFailure()) {
            List<StructuredTaskScope.Subtask<String>> subs = new ArrayList<>(tasks);
            for (int i = 0; i < tasks; i++) {
                final int id = i;
                subs.add(scope.fork(() -> runTask(id, taskMs, failIndex, failAfterMs, cancel)));
            }

            // 父作用域 deadline：joinUntil 超时返回后必须自己 shutdown + 广播取消
            if (timeoutMs > 0) {
                try {
                    scope.joinUntil(Instant.now().plusMillis(timeoutMs));
                } catch (TimeoutException e) {
                    timedOut[0] = true;
                    cancel.set(true);
                    scope.shutdown();
                    scope.join();
                }
            } else {
                scope.join();
            }

            for (int i = 0; i < subs.size(); i++) {
                StructuredTaskScope.Subtask<String> st = subs.get(i);
                switch (st.state()) {
                    case SUCCESS -> outcomes[i] = st.get();
                    case FAILED -> {
                        outcomes[i] = "failed";
                        failed.incrementAndGet();
                    }
                    case UNAVAILABLE -> outcomes[i] = "cancelled";
                }
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            for (int i = 0; i < tasks; i++) {
                if (outcomes[i] == null) {
                    outcomes[i] = "cancelled";
                }
            }
        }

        List<Integer> completedIds = new ArrayList<>();
        List<Integer> cancelledIds = new ArrayList<>();
        int failedId = -1;
        for (int i = 0; i < tasks; i++) {
            String o = outcomes[i] == null ? "cancelled" : outcomes[i];
            switch (o) {
                case "completed" -> completedIds.add(i);
                case "failed" -> failedId = i;
                default -> cancelledIds.add(i);
            }
        }

        String outcome;
        if (failedId >= 0) {
            outcome = "failed";
        } else if (!cancelledIds.isEmpty() || timedOut[0]) {
            outcome = "timeout";
        } else {
            outcome = "completed";
        }

        return new FanoutResponse("java", tasks, taskMs, failIndex, failAfterMs, timeoutMs,
                outcome, completedIds, cancelledIds, failedId,
                System.currentTimeMillis() - t0, active.get());
    }

    /** 子任务：跑满 ms 返回 completed；期间收到取消标志返回 cancelled。 */
    private String runTask(int id, int taskMs, int failIndex, int failAfterMs, AtomicBoolean cancel)
            throws InterruptedException {
        started.incrementAndGet();
        active.incrementAndGet();
        try {
            if (id == failIndex) {
                if (!sleepUntil(failAfterMs, cancel)) {
                    return "cancelled";   // 还没来得及失败就被超时取消
                }
                // 兜底路径：显式置位取消标志（中断之外的一道保险，见类注释）
                cancel.set(true);
                throw new IllegalStateException("task " + id + " failed as requested");
            }
            if (!sleepUntil(taskMs, cancel)) {
                cancelled.incrementAndGet();
                return "cancelled";
            }
            completed.incrementAndGet();
            return "completed";
        } catch (InterruptedException e) {
            // 作用域收尾时中断了本任务（StructuredTaskScope 的实际取消手段）：归一化成 cancelled
            cancelled.incrementAndGet();
            return "cancelled";
        } finally {
            active.decrementAndGet();
        }
    }

    /**
     * 可中断的等待：轮询取消标志（JDK 21 的作用域不会中断子任务线程，只能自己看标志）。
     * 这是 Java 侧"取消传播"的全部实现成本 —— 每一个等待点都要改成这种循环。
     */
    private boolean sleepUntil(long ms, AtomicBoolean cancel) throws InterruptedException {
        long deadline = System.currentTimeMillis() + ms;
        while (System.currentTimeMillis() < deadline) {
            if (cancel.get()) {
                return false;
            }
            long remaining = deadline - System.currentTimeMillis();
            Thread.sleep(Math.min(POLL_MS, Math.max(1, remaining)));
        }
        return !cancel.get();
    }
}
