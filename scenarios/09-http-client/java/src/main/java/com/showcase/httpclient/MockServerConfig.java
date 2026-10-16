package com.showcase.httpclient;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.boot.web.embedded.tomcat.TomcatServletWebServerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.Executors;

/**
 * 内置 Mock 目标服务（Java 原生 HttpServer，端口 8200）
 *
 * 提供 3 个端点测试 HTTP 客户端的不同场景：
 * - /ok    → 200 OK，立即返回
 * - /slow  → 200 OK，但延迟 2s（触发超时测试）
 * - /fail  → 500 Internal Server Error（触发重试测试）
 */
@Configuration
public class MockServerConfig {

    private HttpServer mockServer;
    private int mockPort = 8200;

    @Bean
    public Object mockServerStarter() {
        // 占位 bean，实际启动在 @PostConstruct 里
        return new Object();
    }

    @PostConstruct
    public void start() throws IOException {
        try {
            mockServer = HttpServer.create(new InetSocketAddress(mockPort), 0);
            mockServer.setExecutor(Executors.newFixedThreadPool(4));

            // /ok → 200
            mockServer.createContext("/ok", exch -> jsonResponse(exch, 200, "{\"ok\":true,\"service\":\"mock\"}"));

            // /slow → 延迟 2s
            mockServer.createContext("/slow", exch -> {
                try { Thread.sleep(2000); } catch (InterruptedException ignored) {}
                jsonResponse(exch, 200, "{\"ok\":true,\"slow\":true}");
            });

            // /fail → 500
            mockServer.createContext("/fail", exch -> jsonResponse(exch, 500, "{\"error\":\"mock failure\"}"));

            mockServer.start();
            System.out.println("[MockServer] Java mock server started on http://localhost:" + mockPort);
        } catch (Exception e) {
            System.err.println("[MockServer] failed: " + e.getMessage());
        }
    }

    @PreDestroy
    public void stop() {
        if (mockServer != null) {
            mockServer.stop(0);
        }
    }

    private void jsonResponse(HttpExchange exch, int code, String body) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exch.getResponseHeaders().set("Content-Type", "application/json; charset=utf-8");
        exch.sendResponseHeaders(code, bytes.length);
        try (OutputStream os = exch.getResponseBody()) {
            os.write(bytes);
        }
    }
}
