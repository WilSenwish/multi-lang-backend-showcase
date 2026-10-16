package com.showcase.shutdown.config;

import com.showcase.shutdown.controller.ShutdownController;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationListener;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.stereotype.Component;

import java.util.concurrent.TimeUnit;

/**
 * Java 优雅关闭处理器
 *
 * 核心设计：监听 ContextClosedEvent → 等待 in-flight 请求完成 → 释放资源
 *
 * Java 优雅关闭特点：
 * 1. Spring Boot 默认支持（2.3+），但 SpringBoot 2.1.x 需要自己配置
 * 2. 监听 ContextClosedEvent（Spring Context 关闭事件）
 * 3. 用 CountDownLatch 或 ThreadPoolExecutor.awaitTermination 等待
 * 4. JVM shutdown hook：Runtime.getRuntime().addShutdownHook()
 *
 * 常见坑（Java 开发者）：
 * - 忘了配置 Tomcat 的 connection-timeout → 正在处理的请求可能被强制断开
 * - shutdown hook 顺序问题（数据库连接先关了，还在处理请求就炸了）
 * - 没有超时保护 → 永远等不完
 */
@Component
public class ShutdownConfig implements ApplicationListener<ContextClosedEvent> {

    private static final Logger log = LoggerFactory.getLogger(ShutdownConfig.class);
    private static final long WAIT_TIMEOUT_SECONDS = 10;

    @Autowired
    private ShutdownController controller;

    @Override
    public void onApplicationEvent(ContextClosedEvent event) {
        log.info("========================================");
        log.info("[GRACEFUL SHUTDOWN] ContextClosedEvent received");
        log.info("[GRACEFUL SHUTDOWN] Step 1/4: 标记 shutting_down=true");
        controller.markShuttingDown();

        log.info("[GRACEFUL SHUTDOWN] Step 2/4: 停止接收新请求（由 Spring Boot 自动处理）");

        log.info("[GRACEFUL SHUTDOWN] Step 3/4: 等待 in-flight 请求完成 (timeout={}s)", WAIT_TIMEOUT_SECONDS);
        try {
            long start = System.currentTimeMillis();
            // 轮询等待 in-flight 清零，超时保护
            while (controller.getInFlightCount() > 0
                    && System.currentTimeMillis() - start < WAIT_TIMEOUT_SECONDS * 1000) {
                log.info("[GRACEFUL SHUTDOWN]   等待 {} 个请求完成...", controller.getInFlightCount());
                TimeUnit.MILLISECONDS.sleep(200);
            }

            if (controller.getInFlightCount() > 0) {
                log.warn("[GRACEFUL SHUTDOWN] ⚠️ 超时！还有 {} 个请求未完成，强制关闭",
                        controller.getInFlightCount());
            } else {
                log.info("[GRACEFUL SHUTDOWN] ✅ 所有请求完成");
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }

        log.info("[GRACEFUL SHUTDOWN] Step 4/4: 释放资源（Spring Bean 自动清理）");
        log.info("[GRACEFUL SHUTDOWN] ✅ Shutdown complete");
        log.info("========================================");
    }
}
