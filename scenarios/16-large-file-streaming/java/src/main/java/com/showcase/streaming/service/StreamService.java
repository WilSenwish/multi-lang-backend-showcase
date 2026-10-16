package com.showcase.streaming.service;

import com.showcase.streaming.dto.StreamResponse;
import org.springframework.stereotype.Service;

import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.lang.management.ManagementFactory;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.security.MessageDigest;

/**
 * 场景 16：大文件流式处理 —— Java 用固定大小缓冲 + 手写行边界处理。
 *
 * <p>语义契约（五门语言必须逐字一致，见场景 README）：
 * <ol>
 *   <li>生成一个确定性的定长行文件（每行 10 字节 {@code NNN,AAAAA\n}），生成过程本身也是流式的</li>
 *   <li>以 {@code chunk_kib × 1024} 字节的固定缓冲读取，<b>绝不整体读入内存</b></li>
 *   <li>行可能跨越 chunk 边界 → 用"残余行拼接"处理，不能假设 chunk 边界 = 行边界</li>
 *   <li>逐行解析 amount，过滤 {@code amount >= min_amount}，输出 {@code NNN,BBBBBB\n}（11 字节），流式写</li>
 *   <li>输入/输出各算一份 SHA-256（取前 8 字节 hex），处理完删除两个临时文件</li>
 * </ol>
 *
 * <p><b>Java 侧的关键取舍</b>：
 * 默认写法（{@code Files.readString} / {@code BufferedReader.lines()} / {@code line.split(",")}）
 * 每一行都会产生 String 与 String[] —— 3 百万行就是 3 百万次分配。
 * 那样写"内存峰值"不会爆，但 GC 压力与 RSS 抖动都会随数据量增长，
 * 流式省下的内存又被垃圾吃回去了。
 * 所以这里<b>全程在 byte[] 上手工解析</b>：数字自己算、定宽输出自己填，
 * 处理过程中不产生任何与行数成正比的对象。
 *
 * <p>另一个 Java 特有的代价：<b>标准库没有 RSS 接口</b>。
 * {@code OperatingSystemMXBean} 只给"已提交虚拟内存"，拿不到常驻集，
 * 只能 fork 一次 {@code ps} 采样（见 {@link #rssBytes()}）—— 比其它四门语言都笨重。
 */
@Service
public class StreamService {

    /** 确定性数据序列：h(i) = (i+1)*MULT + INC（mod 2^64），amount = (h >>> 32) % 100000 */
    private static final long MULT = 6364136223846793005L;
    private static final long INC = 1442695040888963407L;
    private static final int LINE_IN = 10;    // "%03d,%05d\n"
    private static final int LINE_OUT = 11;   // "%03d,%06d\n"（amount*2 可能 6 位）
    private static final int GEN_BUF = 64 * 1024;

    public StreamResponse process(int sizeMb, int chunkKib, int minAmount) throws Exception {
        int chunk = chunkKib * 1024;
        long lines = (long) sizeMb * 1024 * 1024 / LINE_IN;

        String tag = "stream16-" + ProcessHandle.current().pid() + "-" + System.nanoTime();
        Path src = Paths.get(System.getProperty("java.io.tmpdir"), tag + ".in");
        Path dst = Paths.get(System.getProperty("java.io.tmpdir"), tag + ".out");

        long rssBefore = rssBytes();
        long tAll = System.nanoTime();

        generate(src, lines);
        long genMs = (System.nanoTime() - tAll) / 1_000_000L;

        MessageDigest hIn = MessageDigest.getInstance("SHA-256");
        MessageDigest hOut = MessageDigest.getInstance("SHA-256");
        long[] stat = new long[6]; // bytesRead, linesRead, bytesWritten, linesWritten, chunks, procMs
        long tProc = System.nanoTime();
        try (InputStream in = new FileInputStream(src.toFile());
             OutputStream out = new FileOutputStream(dst.toFile())) {
            transform(in, out, chunk, minAmount, hIn, hOut, stat);
        }
        stat[5] = (System.nanoTime() - tProc) / 1_000_000L;

        // 真实写出的字节数（stat 文件，而不是信任计数器）—— 计数器可能与真实写入脱节
        long outputFileBytes = -1;
        try {
            outputFileBytes = Files.size(dst);
        } catch (IOException ignored) {
            // 保持 -1
        }

        // 清理临时文件：不删的话多跑几次就把磁盘撑满了
        boolean existed = Files.exists(src);
        Files.deleteIfExists(src);
        Files.deleteIfExists(dst);
        boolean cleanup = existed && !Files.exists(src) && !Files.exists(dst);

        long elapsedMs = (System.nanoTime() - tAll) / 1_000_000L;
        long rssPeak = rssBytes();
        double throughput = stat[5] > 0 ? (stat[0] / (1024.0 * 1024.0)) / (stat[5] / 1000.0) : 0.0;

        return new StreamResponse(
                "java", sizeMb, chunkKib, minAmount,
                stat[0], stat[1], stat[2], stat[3], outputFileBytes,
                hex8(hIn.digest()), hex8(hOut.digest()), stat[4],
                genMs, stat[5], elapsedMs, throughput,
                rssBefore, rssPeak, rssPeak - rssBefore,
                heapBytes(),
                "java.MemoryMXBean.HeapMemoryUsage.used（JVM 堆，不含堆外与元空间）",
                cleanup);
    }

    // ---- 阶段一：流式生成源文件（固定缓冲 64KiB） --------------------------
    private void generate(Path path, long lines) throws IOException {
        try (OutputStream os = new FileOutputStream(path.toFile())) {
            byte[] buf = new byte[GEN_BUF];
            int len = 0;
            long h = INC;
            for (long i = 0; i < lines; i++) {
                h += MULT; // long 溢出即 mod 2^64
                int amount = (int) ((h >>> 32) % 100_000L);
                int g = (int) (i % 1000);
                if (len + LINE_IN > buf.length) {
                    os.write(buf, 0, len);
                    len = 0;
                }
                buf[len++] = (byte) ('0' + g / 100);
                buf[len++] = (byte) ('0' + (g / 10) % 10);
                buf[len++] = (byte) ('0' + g % 10);
                buf[len++] = ',';
                len = appendFixed(buf, len, amount, 5);
                buf[len++] = '\n';
            }
            if (len > 0) {
                os.write(buf, 0, len);
            }
        }
    }

    // ---- 阶段二：读 → 解析 → 过滤 → 转换 → 写 ----------------------------
    private void transform(InputStream in, OutputStream out, int chunk, int minAmount,
                           MessageDigest hIn, MessageDigest hOut, long[] stat) throws IOException {
        byte[] buf = new byte[chunk];
        // pending 保存"上一个 chunk 剩下的半行"，容量固定 → 内存占用与文件大小无关
        byte[] pending = new byte[chunk + LINE_IN];
        int pendingLen = 0;
        byte[] outBuf = new byte[chunk + LINE_OUT];
        int outLen = 0;

        while (true) {
            // readNBytes 会尽量读满 len（与 Go/Rust 的裸 read 不同，Java 这边自带填充循环）
            int n = in.readNBytes(buf, 0, chunk);
            if (n == 0) {
                break;
            }
            stat[4]++;                 // chunks
            stat[0] += n;              // bytesRead
            hIn.update(buf, 0, n);

            System.arraycopy(buf, 0, pending, pendingLen, n);
            pendingLen += n;

            int start = 0;
            for (int i = 0; i < pendingLen; i++) {
                if (pending[i] != '\n') {
                    continue;
                }
                stat[1]++;             // linesRead
                if (i - start >= LINE_IN - 1) {
                    // 直接从字节解析 amount（offset 4..8），不构造 String、不 split
                    int amount = 0;
                    for (int k = start + 4; k < start + 9; k++) {
                        amount = amount * 10 + (pending[k] - '0');
                    }
                    if (amount >= minAmount) {
                        System.arraycopy(pending, start, outBuf, outLen, 4); // "NNN," 原样拷贝
                        outLen += 4;
                        outLen = appendFixed(outBuf, outLen, amount * 2, 6);
                        outBuf[outLen++] = '\n';
                        stat[3]++;                 // linesWritten
                        stat[2] += LINE_OUT;       // bytesWritten
                        if (outLen + LINE_OUT > outBuf.length) {
                            hOut.update(outBuf, 0, outLen);
                            out.write(outBuf, 0, outLen);
                            outLen = 0;
                        }
                    }
                }
                start = i + 1;
            }
            if (start > 0) {
                System.arraycopy(pending, start, pending, 0, pendingLen - start);
                pendingLen -= start;
            }
            if (n < chunk) {           // 没读满 = EOF
                break;
            }
        }
        if (outLen > 0) {
            hOut.update(outBuf, 0, outLen);
            out.write(outBuf, 0, outLen);
        }
    }

    /** 手写定宽数字：不产生 String，也不走 String.format（后者每行都要分配） */
    private static int appendFixed(byte[] b, int pos, int v, int width) {
        for (int k = width - 1; k >= 0; k--) {
            b[pos + k] = (byte) ('0' + v % 10);
            v /= 10;
        }
        return pos + width;
    }

    private static String hex8(byte[] digest) {
        StringBuilder sb = new StringBuilder(16);
        for (int i = 0; i < 8; i++) {
            sb.append(String.format("%02x", digest[i]));
        }
        return sb.toString();
    }

    /**
     * 进程 RSS（字节）。<b>Java 标准库没有这个接口</b>：
     * {@code OperatingSystemMXBean} 只有"已提交的虚拟内存"，与常驻集不是一回事；
     * 只能 fork 一次 ps 采样。ps 输出单位是 KB。
     */
    private static long rssBytes() {
        try {
            Process p = new ProcessBuilder("ps", "-o", "rss=", "-p",
                    Long.toString(ProcessHandle.current().pid()))
                    .redirectErrorStream(true)
                    .start();
            String out = new String(p.getInputStream().readAllBytes(), StandardCharsets.UTF_8).trim();
            p.waitFor();
            if (out.isEmpty()) {
                return -1;
            }
            return Long.parseLong(out.split("\\s+")[0]) * 1024L;
        } catch (Exception e) {
            return -1;
        }
    }

    private static long heapBytes() {
        return ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed();
    }
}
