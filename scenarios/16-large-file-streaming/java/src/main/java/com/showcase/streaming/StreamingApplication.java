package com.showcase.streaming;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/** 场景 16：大文件流式处理（Java）。契约与实现见 {@link com.showcase.streaming.service.StreamService}。 */
@SpringBootApplication
public class StreamingApplication {
    public static void main(String[] args) {
        SpringApplication.run(StreamingApplication.class, args);
    }
}
