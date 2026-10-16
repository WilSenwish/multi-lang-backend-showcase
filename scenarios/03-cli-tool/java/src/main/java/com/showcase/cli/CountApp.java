package com.showcase.cli;

import picocli.CommandLine;
import picocli.CommandLine.Command;
import picocli.CommandLine.Option;
import picocli.CommandLine.Parameters;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;

/**
 * 场景 03：命令行工具 — Java 实现 (Picocli)
 *
 * 简化版 wc：统计文件行数、词数、字符数
 *
 * Java CLI 工具特点：
 * 1. Picocli 是目前 Java 生态最流行的命令行解析库
 * 2. 打包成可执行 jar 需要 maven-shade-plugin / spring-boot-maven-plugin
 * 3. 启动速度慢（JVM 冷启动 ~100-500ms）
 * 4. 运行时需要 JRE（GraalVM Native Image 可解决）
 *
 * 和 Go/Rust 原生二进制对比：
 * - 启动慢 10-100x
 * - 不需要预编译（写了就能跑）
 * - 依赖多（即使简单 CLI，fat-jar 也要 5-10MB）
 */
@Command(
        name = "count",
        mixinStandardHelpOptions = true,
        version = "1.0.0",
        description = "简化版 wc — 统计文件行数、词数、字符数"
)
public class CountApp implements Callable<Integer> {

    @Option(names = "-l", description = "只统计行数 (lines)")
    boolean showLines;

    @Option(names = "-w", description = "只统计词数 (words)")
    boolean showWords;

    @Option(names = "-c", description = "只统计字符数 (chars)")
    boolean showChars;

    @Parameters(arity = "1..*", description = "要统计的文件路径，支持多个")
    List<String> files = new ArrayList<>();

    public static void main(String[] args) {
        int exitCode = new CommandLine(new CountApp()).execute(args);
        System.exit(exitCode);
    }

    @Override
    public Integer call() {
        // 如果没指定任何选项，默认显示全部
        boolean anyFlag = showLines || showWords || showChars;
        boolean defaultAll = !anyFlag;

        // 统计结果
        long totalLines = 0;
        long totalWords = 0;
        long totalChars = 0;

        // 支持单文件或多文件
        for (String filePath : files) {
            Path path = Paths.get(filePath);
            if (!Files.exists(path)) {
                System.err.println("count: 无法打开文件 '" + filePath + "': 文件不存在");
                return 1;
            }
            if (!Files.isRegularFile(path)) {
                System.err.println("count: '" + filePath + "' 不是普通文件");
                return 1;
            }

            try {
                String content = Files.readString(path);

                // 行数：以 \n 分割的段数（最后一行没有 \n 也算）
                long lines = content.lines().count();

                // 词数：空白字符分割的非空段数
                long words = content.isBlank() ? 0
                        : java.util.Arrays.stream(content.trim().split("\\s+")).count();

                // 字符数：String.length() → UTF-16 单元数
                long chars = content.length();

                if (files.size() > 1) {
                    // 多文件：每个文件单独一行，最后 total
                    printResult(filePath, lines, words, chars, defaultAll);
                }

                totalLines += lines;
                totalWords += words;
                totalChars += chars;
            } catch (IOException e) {
                System.err.println("count: 读取 '" + filePath + "' 失败: " + e.getMessage());
                return 1;
            }
        }

        if (files.size() > 1) {
            System.out.println("---");
        }

        // 输出汇总
        if (files.size() == 1) {
            printResult(null, totalLines, totalWords, totalChars, defaultAll);
        } else {
            printResult("total", totalLines, totalWords, totalChars, defaultAll);
        }

        return 0;
    }

    private void printResult(String label, long lines, long words, long chars, boolean defaultAll) {
        StringBuilder sb = new StringBuilder();
        if (showLines || defaultAll) sb.append("lines=").append(lines).append(" ");
        if (showWords || defaultAll) sb.append("words=").append(words).append(" ");
        if (showChars || defaultAll) sb.append("chars=").append(chars);

        // 尾部清理多余空格
        String out = sb.toString().trim();
        if (label != null) {
            System.out.println(out + "  " + label);
        } else {
            System.out.println(out);
        }
    }
}
