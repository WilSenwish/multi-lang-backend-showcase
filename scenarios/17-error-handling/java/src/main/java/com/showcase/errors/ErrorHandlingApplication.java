package com.showcase.errors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * 场景 17：错误处理深水区 —— Java 版本。
 *
 * <p>统一契约见场景 README；本实现的取舍写在 {@code GlobalExceptionHandler} 与
 * {@code ErrorController} 的注释里。
 */
@SpringBootApplication
public class ErrorHandlingApplication {
    public static void main(String[] args) {
        SpringApplication.run(ErrorHandlingApplication.class, args);
    }
}
