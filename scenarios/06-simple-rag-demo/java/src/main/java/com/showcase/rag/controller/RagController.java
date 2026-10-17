package com.showcase.rag.controller;

import com.showcase.rag.service.RagService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.io.IOException;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 场景 06：轻量 RAG Demo — 3 个端点
 *
 * POST /ingest — 摄入文档
 * POST /ask    — 问答（检索 + 生成）
 * GET  /health — 健康检查 + 状态
 */
@RestController
public class RagController {

    @Autowired
    private RagService ragService;

    /**
     * POST /ingest — 摄入文档
     * body: {"file_path": "./docs/philosophy.md"}
     */
    @PostMapping("/ingest")
    public ResponseEntity<Map<String, Object>> ingest(@RequestBody Map<String, String> body) {
        Map<String, Object> resp = new LinkedHashMap<>();
        try {
            String filePath = body.get("file_path");
            if (filePath == null || filePath.isEmpty()) {
                resp.put("success", false);
                resp.put("error", "缺少 file_path");
                return ResponseEntity.badRequest().body(resp);
            }

            int chunks = ragService.ingestFile(filePath);
            resp.put("success", true);
            resp.put("file", filePath);
            resp.put("chunks", chunks);
            resp.put("embeddings_generated", chunks);
            resp.put("vocab_size", ragService.vocabSize());
        } catch (IOException e) {
            // 文件不存在/是目录/权限问题都是客户端给的 path 不对 → 400（与 Go/Python/Rust/TS 一致）
            resp.put("success", false);
            resp.put("error", e.getMessage());
            return ResponseEntity.badRequest().body(resp);
        }
        return ResponseEntity.ok(resp);
    }

    /**
     * POST /ask — 问答
     * body: {"question": "Rust 的所有权是什么？", "top_k": 3}
     */
    @PostMapping("/ask")
    public ResponseEntity<Map<String, Object>> ask(@RequestBody Map<String, Object> body) {
        Map<String, Object> resp = new LinkedHashMap<>();

        Object qObj = body.get("question");
        if (!(qObj instanceof String)) {
            resp.put("success", false);
            resp.put("error", "缺少 question");
            return ResponseEntity.badRequest().body(resp);
        }
        String question = (String) qObj;

        // top_k 缺省 3；显式传值必须是 >= 1 的整数（Jackson 可能给 Integer/Long/Double，逐个安全转换）
        int topK = 3;
        Object tkObj = body.get("top_k");
        if (tkObj != null) {
            try {
                if (tkObj instanceof Integer || tkObj instanceof Long) {
                    topK = ((Number) tkObj).intValue();
                } else if (tkObj instanceof Double && ((Double) tkObj) % 1.0 == 0) {
                    topK = ((Double) tkObj).intValue();
                } else {
                    throw new IllegalArgumentException("top_k 必须是整数");
                }
            } catch (Exception e) {
                resp.put("success", false);
                resp.put("error", "top_k 必须是 >= 1 的整数");
                return ResponseEntity.badRequest().body(resp);
            }
            if (topK < 1) {
                resp.put("success", false);
                resp.put("error", "top_k 必须是 >= 1 的整数");
                return ResponseEntity.badRequest().body(resp);
            }
        }

        // 检索
        List<Map<String, Object>> sources = ragService.search(question, topK);

        // 生成答案（当前是 mock，真实场景可调用 LLM）
        String answer = ragService.mockAnswer(question, sources);

        resp.put("success", true);
        resp.put("question", question);
        resp.put("answer", answer);
        resp.put("sources", sources);
        resp.put("mode", "local-mock"); // 标明是本地 mock 还是真实 LLM
        return ResponseEntity.ok(resp);
    }

    /**
     * GET /health — 健康检查 + 状态
     */
    @GetMapping("/health")
    public Map<String, Object> health() {
        Map<String, Object> resp = new LinkedHashMap<>();
        resp.put("service", "simple-rag-java");
        resp.put("chunks_loaded", ragService.chunkCount());
        resp.put("vocab_size", ragService.vocabSize());
        return resp;
    }
}
