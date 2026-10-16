// Package main 场景 03：命令行工具 — Go 实现（简化版 wc）
//
// Go CLI 工具特点：
// 1. 标准库 flag 解析参数，零第三方依赖
// 2. go build 直接编译出原生静态二进制，无运行时依赖
// 3. 启动速度极快（~1ms 级别）
// 4. 二进制大小小（10-20MB，无 JVM）
//
// 和 Java 对比：
// - Go 编译快，Java 依赖多编译慢
// - Go 单文件分发，Java 需要 JRE 或 fat-jar
// - Go 标准库 flag 简单但功能有限，Java Picocli 功能丰富
package main

import (
	"bufio"
	"flag"
	"fmt"
	"os"
	"strings"
)

func main() {
	// ====== 参数解析（零依赖，标准库 flag） ======
	showLines := flag.Bool("l", false, "只统计行数 (lines)")
	showWords := flag.Bool("w", false, "只统计词数 (words)")
	showChars := flag.Bool("c", false, "只统计字符数 (chars)")
	flag.Usage = func() {
		fmt.Fprintln(os.Stderr, "用法: count [选项] <文件...>")
		fmt.Fprintln(os.Stderr, "")
		fmt.Fprintln(os.Stderr, "简化版 wc — 统计文件行数、词数、字符数")
		fmt.Fprintln(os.Stderr, "")
		fmt.Fprintln(os.Stderr, "选项:")
		flag.PrintDefaults()
		fmt.Fprintln(os.Stderr, "  -h    帮助信息")
	}
	flag.Parse()

	// 获取文件参数
	files := flag.Args()
	if len(files) == 0 {
		fmt.Fprintln(os.Stderr, "count: 需要指定至少一个文件")
		os.Exit(2)
	}

	// 如果没指定任何选项，默认全显示
	anyFlag := *showLines || *showWords || *showChars
	defaultAll := !anyFlag

	var totalLines, totalWords, totalChars int64

	for _, filePath := range files {
		lines, words, chars, err := countFile(filePath)
		if err != nil {
			fmt.Fprintf(os.Stderr, "count: %v\n", err)
			os.Exit(1)
		}

		if len(files) > 1 {
			printResult(filePath, lines, words, chars, *showLines, *showWords, *showChars, defaultAll)
		}

		totalLines += lines
		totalWords += words
		totalChars += chars
	}

	if len(files) > 1 {
		fmt.Fprintln(os.Stderr, "---")
	}

	label := ""
	if len(files) > 1 {
		label = "total"
	}
	printResult(label, totalLines, totalWords, totalChars, *showLines, *showWords, *showChars, defaultAll)
}

// countFile 统计单个文件的 lines/words/chars
func countFile(path string) (lines, words, chars int64, err error) {
	f, err := os.Open(path)
	if err != nil {
		return 0, 0, 0, fmt.Errorf("无法打开 '%s': %v", path, err)
	}
	defer f.Close()

	// 逐行读（节省内存，大文件也 OK）
	reader := bufio.NewReader(f)
	for {
		line, err := reader.ReadString('\n')
		if err != nil && err.Error() != "EOF" {
			break
		}
		if line == "" && err != nil {
			break
		}

		// 行数：每个 \n 计数
		lines++

		// 字符数：len(line) 是 UTF-8 字节数
		// 但 wc 按字符数统计，Go 里用 len([]rune(line)) 更准确
		chars += int64(len([]rune(line)))

		// 词数：按空白分割
		lineWords := strings.Fields(line)
		words += int64(len(lineWords))

		if err != nil { // EOF
			break
		}
	}

	return
}

func printResult(label string, lines, words, chars int64, showLines, showWords, showChars, defaultAll bool) {
	var b strings.Builder

	if showLines || defaultAll {
		fmt.Fprintf(&b, "lines=%d ", lines)
	}
	if showWords || defaultAll {
		fmt.Fprintf(&b, "words=%d ", words)
	}
	if showChars || defaultAll {
		fmt.Fprintf(&b, "chars=%d", chars)
	}

	out := strings.TrimSpace(b.String())
	if label != "" {
		fmt.Printf("%s  %s\n", out, label)
	} else {
		fmt.Println(out)
	}
}
