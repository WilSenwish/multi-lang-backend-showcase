package com.showcase.concurrent;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * 场景 02：并发任务处理 — 启动类
 */
@SpringBootApplication
public class ConcurrentTaskApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConcurrentTaskApplication.class, args);
    }
}
