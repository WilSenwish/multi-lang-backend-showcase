package com.showcase.errors.service;

import org.springframework.stereotype.Component;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

/** 进程内计数器：区分"被处理器接住的错误"与"无人认领的异步错误"。 */
@Component
public class ErrorState {

    private final AtomicInteger handled = new AtomicInteger();
    private final AtomicInteger unhandled = new AtomicInteger();
    private final AtomicInteger panics = new AtomicInteger();
    private final AtomicInteger seq = new AtomicInteger();

    private volatile String lastUnhandled = "";
    private volatile String lastTraceId = "";

    /** 只用于演示的后台线程池：真实项目里应当交给容器管理的 TaskExecutor。 */
    public final ExecutorService detachedPool = Executors.newFixedThreadPool(2);

    public void noteHandled() {
        handled.incrementAndGet();
    }

    public void notePanic() {
        handled.incrementAndGet();
        panics.incrementAndGet();
    }

    public void noteUnhandled(String message) {
        unhandled.incrementAndGet();
        lastUnhandled = message;
    }

    public int handled() {
        return handled.get();
    }

    public int unhandled() {
        return unhandled.get();
    }

    public int panics() {
        return panics.get();
    }

    public String lastUnhandled() {
        return lastUnhandled;
    }

    public String lastTraceId() {
        return lastTraceId;
    }

    public void lastTraceId(String id) {
        this.lastTraceId = id;
    }

    public int nextSeq() {
        return seq.incrementAndGet();
    }
}
