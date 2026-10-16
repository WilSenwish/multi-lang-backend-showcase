package com.showcase.fileio.controller;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;

/**
 * 场景 04：文件读写 & 目录遍历 — Java 实现
 *
 * Java 文件 IO 特点：
 * 1. java.nio.file.Files 是 Java 7+ 的新标准（推荐）
 * 2. 同步 API，但 Spring Boot 默认也能处理
 * 3. Path 是不可变的，链式操作方便
 * 4. Files.walkFileTree + SimpleFileVisitor 实现递归遍历
 * 5. Files.write / Files.readAllBytes / Files.readString 非常方便
 *
 * 和其他语言对比：
 * - Java NIO.2 功能最全，Stream API + Files 组合非常灵活
 * - Go os 包同步 + 简单
 * - Python pathlib 面向对象 + aiofiles 异步
 * - Rust std::fs 同步 + tokio::fs 异步 + walkdir 递归
 * - TS Node fs/promises 原生异步
 */
@RestController
@RequestMapping("/file")
public class FileIoController {

    /** content 为对象时序列化为规范 JSON（紧凑分隔符、非 ASCII 不转义、HTML 字符不转义） */
    private static final ObjectMapper MAPPER = new ObjectMapper();

    /**
     * POST /file/write — 写文件（覆盖或追加）
     * body: {"path": "/tmp/test.json", "content": {...}, "append": false}
     */
    @PostMapping("/write")
    public Map<String, Object> write(@RequestBody Map<String, Object> body) {
        String pathStr = (String) body.get("path");
        Object contentObj = body.get("content");
        // 曾经这里写成 getOrDefault("append", false) instanceof Boolean ? (Boolean) body.get("append") : false
        // —— 键缺失时 getOrDefault 拿到默认值 false 通过检查，但 body.get("append") 返回 null，
        // 拆箱直接 NPE（而且抛在 try 外面，变成 500）。契约用例"不带 append 字段的写"当场抓住。
        Object appendObj = body.get("append");
        boolean append = appendObj instanceof Boolean && (Boolean) appendObj;

        Map<String, Object> resp = new LinkedHashMap<>();
        try {
            Path path = Paths.get(pathStr);

            // 确保父目录存在
            Path parent = path.getParent();
            if (parent != null && !Files.exists(parent)) {
                Files.createDirectories(parent);
            }

            // 把 content 转成字符串写入：
            // - 字符串 → 原样写入
            // - 其他类型 → 规范 JSON（与 Go/Python/Rust/TS 的序列化结果逐字节一致；
            //   曾经这里用 String.valueOf(map) 写出 Java 的 toString 格式 {k=v}，不是 JSON）
            String content = contentObj instanceof String
                    ? (String) contentObj
                    : MAPPER.writeValueAsString(contentObj);

            byte[] data = content.getBytes(java.nio.charset.StandardCharsets.UTF_8);
            OpenOption[] options = append
                    ? new OpenOption[]{StandardOpenOption.CREATE, StandardOpenOption.APPEND}
                    : new OpenOption[]{StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING};

            Files.write(path, data, options);

            resp.put("success", true);
            resp.put("path", pathStr);
            resp.put("bytes_written", data.length);
            resp.put("append", append);
        } catch (Exception e) {
            // 写失败不回 5xx：与其余四门一致，用 200 + success:false 表达领域级失败
            resp.put("success", false);
            resp.put("error", e.getMessage());
        }
        return resp;
    }

    /**
     * GET /file/read — 读文件
     * ?path=/tmp/test.json
     */
    @GetMapping("/read")
    public ResponseEntity<?> read(@RequestParam String path) {
        // 统一契约：path 缺失/为空串 → 400（Spring 对缺失参数本就是 400，空串在此显式补齐）
        if (path == null || path.isBlank()) {
            return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(Map.of("error", "missing path param"));
        }
        try {
            Path p = Paths.get(path);
            if (!Files.exists(p)) {
                return ResponseEntity.status(404).body(Map.of("error", "文件不存在: " + path));
            }
            if (!Files.isRegularFile(p)) {
                return ResponseEntity.status(400).body(Map.of("error", "不是文件: " + path));
            }

            String content = Files.readString(p);
            Map<String, Object> resp = new LinkedHashMap<>();
            resp.put("path", path);
            resp.put("content", content);
            resp.put("bytes", Files.size(p));
            return ResponseEntity.ok(resp);
        } catch (Exception e) {
            return ResponseEntity.status(500).body(Map.of("error", e.getMessage()));
        }
    }

    /**
     * GET /file/scan — 目录遍历（递归/非递归）
     * ?dir=/tmp&recursive=true
     */
    @GetMapping("/scan")
    public ResponseEntity<?> scan(
            @RequestParam String dir,
            @RequestParam(defaultValue = "true") boolean recursive) {
        // 统一契约：dir 缺失/为空串 → 400
        if (dir == null || dir.isBlank()) {
            return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(Map.of("error", "missing dir param"));
        }
        try {
            Path start = Paths.get(dir);
            if (!Files.exists(start)) {
                return ResponseEntity.status(404).body(Map.of("error", "目录不存在: " + dir));
            }
            if (!Files.isDirectory(start)) {
                return ResponseEntity.status(400).body(Map.of("error", "不是目录: " + dir));
            }

            AtomicLong fileCount = new AtomicLong(0);
            AtomicLong totalBytes = new AtomicLong(0);

            if (recursive) {
                // 递归遍历
                Files.walkFileTree(start, new SimpleFileVisitor<Path>() {
                    @Override
                    public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) {
                        if (attrs.isRegularFile()) {
                            fileCount.incrementAndGet();
                            totalBytes.addAndGet(attrs.size());
                        }
                        return FileVisitResult.CONTINUE;
                    }

                    @Override
                    public FileVisitResult visitFileFailed(Path file, IOException exc) {
                        // 忽略权限错误
                        return FileVisitResult.CONTINUE;
                    }
                });
            } else {
                // 非递归 — 用 Files.list 只看一层
                try (var stream = Files.list(start)) {
                    stream.forEach(p -> {
                        try {
                            if (Files.isRegularFile(p)) {
                                fileCount.incrementAndGet();
                                totalBytes.addAndGet(Files.size(p));
                            }
                        } catch (IOException ignored) {
                        }
                    });
                }
            }

            Map<String, Object> resp = new LinkedHashMap<>();
            resp.put("dir", dir);
            resp.put("recursive", recursive);
            resp.put("files", fileCount.get());
            resp.put("total_bytes", totalBytes.get());
            return ResponseEntity.ok(resp);

        } catch (Exception e) {
            return ResponseEntity.status(500).body(Map.of("error", e.getMessage()));
        }
    }
}
