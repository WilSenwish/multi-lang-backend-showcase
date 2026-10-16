package com.showcase.json.controller;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.showcase.json.dto.User;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * 场景 01：JSON 序列化/反序列化控制器
 *
 * 统一接口（5 种语言都实现这 4 个端点）：
 * - GET  /demo        → 返回标准测试 JSON 对象
 * - POST /serialize    → 接收 JSON → 序列化成字符串 → 返回 + 大小
 * - POST /deserialize  → 接收 JSON 字符串 → 反序列化成对象 → 返回
 * - POST /roundtrip    → 接收 JSON → serialize → deserialize → serialize → 返回前后对比
 * - GET  /bench        → 内部 10000 次循环，返回耗时
 */
@Slf4j
@RestController
@RequestMapping("/")
public class JsonController {

    /** Spring Boot 自动配置的 ObjectMapper — Jackson 核心 */
    @Autowired
    private ObjectMapper mapper;

    /**
     * GET /demo — 返回标准测试用 JSON
     * 展示 null 值 / 空数组 / 嵌套对象 / 数组 的序列化行为
     */
    @GetMapping("/demo")
    public User demo() {
        return User.demo();
    }

    /**
     * POST /serialize — 对象 → JSON 字符串
     */
    @PostMapping("/serialize")
    public Map<String, Object> serialize(@RequestBody Map<String, Object> body)
            throws JsonProcessingException {
        long startNs = System.nanoTime();
        String json = mapper.writeValueAsString(body);
        long elapsedUs = (System.nanoTime() - startNs) / 1000;

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("json", json);
        result.put("bytes", json.getBytes().length);
        result.put("time_us", elapsedUs);
        result.put("pretty", mapper.writerWithDefaultPrettyPrinter().writeValueAsString(body));
        return result;
    }

    /**
     * POST /deserialize — JSON 字符串 → 对象
     * 接收格式：{"json_string": "{\"id\":1,\"name\":\"Alice\"}"}
     */
    @PostMapping("/deserialize")
    public Map<String, Object> deserialize(@RequestBody Map<String, String> body)
            throws JsonProcessingException {
        String jsonString = body.get("json_string");
        long startNs = System.nanoTime();
        Object parsed = mapper.readValue(jsonString, Object.class);
        long elapsedUs = (System.nanoTime() - startNs) / 1000;

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("parsed", parsed);
        result.put("time_us", elapsedUs);
        result.put("size", jsonString.getBytes().length);
        return result;
    }

    /**
     * POST /roundtrip — 往返保真测试
     * 对象 → JSON 字符串 → 对象 → JSON 字符串，对比前后是否一致
     */
    @PostMapping("/roundtrip")
    public Map<String, Object> roundtrip(@RequestBody Map<String, Object> body)
            throws JsonProcessingException {
        // 第一次序列化
        String json1 = mapper.writeValueAsString(body);

        // 反序列化
        Object parsed = mapper.readValue(json1, Object.class);

        // 第二次序列化
        String json2 = mapper.writeValueAsString(parsed);

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("original_json", json1);
        result.put("roundtrip_json", json2);
        result.put("equal", json1.equals(json2));
        result.put("original_bytes", json1.getBytes().length);
        result.put("roundtrip_bytes", json2.getBytes().length);
        return result;
    }

    /**
     * GET /bench — 性能基准
     * 10000 次 serialize + 10000 次 deserialize，返回总耗时
     */
    @GetMapping("/bench")
    public Map<String, Object> bench() throws JsonProcessingException {
        User user = User.demo();
        int iterations = 10000;

        // 预热
        for (int i = 0; i < 100; i++) {
            String s = mapper.writeValueAsString(user);
            mapper.readValue(s, Object.class);
        }

        long startNs = System.nanoTime();
        String lastJson = null;
        for (int i = 0; i < iterations; i++) {
            lastJson = mapper.writeValueAsString(user);
            mapper.readValue(lastJson, Object.class);
        }
        long totalMs = (System.nanoTime() - startNs) / 1_000_000;

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("language", "java-jackson");
        result.put("iterations", iterations);
        result.put("total_time_ms", totalMs);
        result.put("avg_time_us", (totalMs * 1000.0 / iterations));
        result.put("json_size_bytes", lastJson != null ? lastJson.getBytes().length : 0);
        return result;
    }
}
