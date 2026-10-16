package com.showcase.httpclient.controller;

import com.showcase.httpclient.service.ExternalApiService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
public class HttpClientController {

    @Autowired
    private ExternalApiService externalApiService;

    @Value("${mock-server.port:8200}")
    private int mockPort;

    /**
     * POST /call-external — 调用外部 API
     */
    @PostMapping("/call-external")
    public Map<String, Object> callExternal(@RequestBody Map<String, Object> body) {
        String url = (String) body.getOrDefault("url", "http://localhost:" + mockPort + "/ok");
        int timeoutMs = (int) body.getOrDefault("timeout_ms", 5000);
        int retryTimes = (int) body.getOrDefault("retry_times", 3);

        return externalApiService.call(url, retryTimes, timeoutMs);
    }

    /**
     * GET /health — 状态
     */
    @GetMapping("/health")
    public Map<String, Object> health() {
        return Map.of("service", "http-client-java", "mock_port", mockPort);
    }
}
