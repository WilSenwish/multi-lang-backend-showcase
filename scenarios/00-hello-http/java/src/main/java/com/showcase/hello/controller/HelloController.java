package com.showcase.hello.controller;

import com.showcase.hello.dto.HelloResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * Hello HTTP 控制器
 * 统一 API 契约:
 *   GET /hello?name={xxx}
 *   → {"msg": "hello {xxx}"}
 *   → {"msg": "hello world"}  // name 缺省
 */
@RestController
public class HelloController {

    private static final String DEFAULT_NAME = "world";

    @GetMapping("/hello")
    public HelloResponse hello(@RequestParam(value = "name", required = false) String name) {
        String target = (name == null || name.isBlank()) ? DEFAULT_NAME : name;
        return new HelloResponse("hello " + target);
    }
}
