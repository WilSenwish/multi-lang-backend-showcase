package com.showcase.concurrency;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * 场景 15：结构化并发 + 取消传播（Java / JDK 21）。
 *
 * <p>本服务需要 JDK 21：{@code java.util.concurrent.StructuredTaskScope} 在 JDK 21 仍是
 * preview API，编译与运行都带 {@code --enable-preview}（见 pom.xml）。
 */
@SpringBootApplication
public class ConcurrencyApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConcurrencyApplication.class, args);
    }
}
