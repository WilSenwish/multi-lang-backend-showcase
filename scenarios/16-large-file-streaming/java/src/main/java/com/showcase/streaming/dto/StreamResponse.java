package com.showcase.streaming.dto;

/**
 * 响应体（JSON 为 snake_case，与其余四门语言逐字一致）。
 *
 * <p>其中 {@code rssDeltaBytes} 是本场景唯一能证明"确实流式"的字段：
 * 若实现退化成"一次性读入"，它会随数据量线性增长。
 */
public record StreamResponse(
        String lang,
        int sizeMb,
        int chunkKib,
        int minAmount,
        long bytesRead,
        long linesRead,
        long bytesWritten,
        long linesWritten,
        long outputFileBytes,
        String checksum,
        String outputChecksum,
        long chunks,
        long genMs,
        long procMs,
        long elapsedMs,
        double throughputMbS,
        long rssBeforeBytes,
        long rssPeakBytes,
        long rssDeltaBytes,
        long peakHeapBytes,
        String heapMetric,
        boolean cleanup) {
}
