package com.showcase.json;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * 场景 01：JSON 序列化/反序列化 — 启动类
 *
 * Java 用 Jackson（spring-boot-starter-json 自动引入）。
 * Jackson 是 Java 生态事实上的 JSON 标准，Spring 默认。
 */
@SpringBootApplication
public class JsonSerializeApplication {
    public static void main(String[] args) {
        SpringApplication.run(JsonSerializeApplication.class, args);
    }
}
