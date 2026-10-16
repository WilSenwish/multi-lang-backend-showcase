package com.showcase.config.controller;

import com.showcase.config.AppConfig;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * GET /config — 返回当前生效的配置（脱敏密码）
 */
@RestController
public class ConfigController {

    @Autowired
    private AppConfig config;

    @GetMapping("/config")
    public Map<String, Object> config() {
        Map<String, Object> resp = new LinkedHashMap<>();

        Map<String, Object> server = new LinkedHashMap<>();
        server.put("port", config.getServer().getPort());
        server.put("host", config.getServer().getHost());
        resp.put("server", server);

        Map<String, Object> database = new LinkedHashMap<>();
        database.put("url", config.getDatabase().getUrl());
        database.put("user", config.getDatabase().getUser());
        database.put("password", "********"); // 脱敏！
        database.put("pool_size", config.getDatabase().getPoolSize());
        resp.put("database", database);

        Map<String, Object> logging = new LinkedHashMap<>();
        logging.put("level", config.getLogging().getLevel());
        logging.put("json", config.getLogging().isJson());
        resp.put("logging", logging);

        resp.put("env", config.getEnv());
        resp.put("source", "Spring Boot @ConfigurationProperties + application.yml");

        return resp;
    }
}
