package com.showcase.rag.service;

import org.springframework.stereotype.Service;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collectors;

/**
 * 极简内存向量存储 + 检索
 *
 * 向量化策略（无外部 API 的 mock fallback）：
 * - 词频向量：统计每个 chunk 中每个词出现的次数
 * - 所有 chunk 合并成词表，每个 chunk 转成固定维度的词频向量
 * - 查询也转成词频向量，cosine similarity 计算相似度
 *
 * 真正的 RAG 应该用 embedding API，但这个简化版展示了核心 pipeline：
 * 切分 → 向量化 → 存储 → 检索 → 生成答案
 */
@Service
public class RagService {

    // 向量存储：chunkId → Chunk（文本 + 词频向量）
    private final Map<String, Chunk> store = new ConcurrentHashMap<>();

    // 全局词表：所有出现过的词，分配固定索引
    private final Set<String> vocab = new LinkedHashSet<>();

    public static class Chunk {
        public final String id;
        public final String text;
        public final String source;
        public double[] vector; // 词频向量(摄入后由 rebuild 重新生成)

        public Chunk(String id, String text, String source, double[] vector) {
            this.id = id;
            this.text = text;
            this.source = source;
            this.vector = vector;
        }
    }

    // ============ 摄入 ============

    /** 从文件摄入文档，返回切分数量 */
    public synchronized int ingestFile(String filePath) throws IOException {
        Path path = Paths.get(filePath);
        if (!Files.exists(path)) {
            throw new IOException("文件不存在: " + filePath);
        }

        String content = Files.readString(path);
        String fileName = path.getFileName().toString();

        // 每次摄入重建 store（与 Go/Python/Rust/TS 一致：最后一次摄入的文档生效）
        store.clear();

        // 按空行切段落（Markdown 自然分段）
        String[] paragraphs = content.split("\n\s*\n");
        int chunkId = 0;

        for (String para : paragraphs) {
            String trimmed = para.trim();
            if (trimmed.length() < 10) continue; // 跳过太短的

            String id = fileName + "#" + chunkId++;
            store.put(id, new Chunk(id, trimmed, fileName, null));
        }

        // 重建词表 + 向量
        rebuildVocabAndVectors();
        return chunkId;
    }

    /** 重建全局词表，给所有 chunk 生成词频向量 */
    private void rebuildVocabAndVectors() {
        // 1. 收集所有词
        Set<String> allWords = new LinkedHashSet<>();
        for (Chunk c : store.values()) {
            allWords.addAll(tokenize(c.text));
        }
        vocab.clear();
        vocab.addAll(allWords);

        // 2. 给所有 chunk 生成向量
        int dim = vocab.size();
        String[] wordList = vocab.toArray(new String[0]);
        for (Chunk c : store.values()) {
            c.vector = buildVector(c.text, wordList, dim);
        }
    }

    // ============ 检索 ============

    /** 检索 top-k 最相关的片段 */
    public List<Map<String, Object>> search(String question, int topK) {
        // 查询也转成词频向量
        int dim = vocab.size();
        if (dim == 0) return List.of();

        String[] wordList = vocab.toArray(new String[0]);
        double[] qVec = buildVector(question, wordList, dim);

        // 计算 cosine similarity
        List<Map<String, Object>> results = new ArrayList<>();
        for (Chunk c : store.values()) {
            double score = cosineSimilarity(qVec, c.vector);
            if (score > 0) {
                Map<String, Object> item = new LinkedHashMap<>();
                item.put("text", c.text);
                item.put("source", c.source);
                item.put("score", Math.round(score * 10000.0) / 10000.0);
                results.add(item);
            }
        }

        // 按 score 降序
        results.sort((a, b) -> Double.compare((double) b.get("score"), (double) a.get("score")));
        return results.stream().limit(topK).collect(Collectors.toList());
    }

    /** Mock 生成答案：把 top 片段拼起来回答（格式与其余四门逐字节一致） */
    public String mockAnswer(String question, List<Map<String, Object>> sources) {
        if (sources.isEmpty()) {
            return "我没有找到相关信息，请先 POST /ingest 摄入文档。";
        }
        StringBuilder sb = new StringBuilder();
        sb.append("根据摄入的文档，关于「").append(question).append("」的相关内容：\n\n");
        for (int i = 0; i < sources.size(); i++) {
            @SuppressWarnings("unchecked")
            Map<String, Object> s = sources.get(i);
            // Locale.ROOT：避免部分区域设置把小数点渲染成逗号；%.4f 与 Go/Python/Rust/TS 对齐
            sb.append(i + 1).append(". (来自 ").append(s.get("source"))
              .append(", 相关度 ").append(String.format(Locale.ROOT, "%.4f", ((Number) s.get("score")).doubleValue()))
              .append(") ").append(s.get("text")).append("\n");
        }
        return sb.toString();
    }

    // ============ 辅助 ============

    /** 简单分词：小写化 + 按非字母数字分割 + 过滤短词 */
    private List<String> tokenize(String text) {
        return Arrays.stream(text.toLowerCase().split("[^a-zA-Z0-9\u4e00-\u9fff]+"))
                .filter(w -> w.length() >= 2)
                .collect(Collectors.toList());
    }

    /** 构建词频向量 */
    private double[] buildVector(String text, String[] vocab, int dim) {
        List<String> tokens = tokenize(text);
        double[] vec = new double[dim];
        // 词频
        Map<String, Long> freq = tokens.stream()
                .collect(Collectors.groupingBy(w -> w, Collectors.counting()));
        for (int i = 0; i < dim; i++) {
            vec[i] = freq.getOrDefault(vocab[i], 0L).doubleValue();
        }
        return vec;
    }

    /** 余弦相似度 */
    private double cosineSimilarity(double[] a, double[] b) {
        double dot = 0, normA = 0, normB = 0;
        for (int i = 0; i < a.length; i++) {
            dot += a[i] * b[i];
            normA += a[i] * a[i];
            normB += b[i] * b[i];
        }
        if (normA == 0 || normB == 0) return 0;
        return dot / (Math.sqrt(normA) * Math.sqrt(normB));
    }

    // ============ 状态 ============

    public int chunkCount() { return store.size(); }
    public int vocabSize() { return vocab.size(); }
}
