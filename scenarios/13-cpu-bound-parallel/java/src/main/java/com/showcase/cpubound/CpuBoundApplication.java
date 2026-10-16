package com.showcase.cpubound;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * 场景 13：CPU 密集并行计算 — 启动类
 *
 * <p>本场景是场景 02（IO 密集并发）的姊妹篇：任务体不再 sleep，而是纯计算。
 * IO 密集时四门"真并行"语言拉不开差距，CPU 密集才是它们的分水岭。
 */
@SpringBootApplication
public class CpuBoundApplication {

    public static void main(String[] args) {
        SpringApplication.run(CpuBoundApplication.class, args);
    }
}
