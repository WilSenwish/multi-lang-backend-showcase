/**
 * 场景 16：大文件流式处理 —— Go 用固定大小缓冲 + 手写行边界处理。
 *
 * 语义契约（五门语言必须逐字一致，见场景 README）：
 *   1. 生成一个确定性的定长行文件（每行 10 字节：NNN,AAAAA\n），生成过程本身也是流式的
 *   2. 以 chunk_kib × 1024 字节的固定缓冲读取，**绝不整体读入内存**
 *   3. 行可能跨越 chunk 边界 → 必须用"残余行拼接"处理，不能假设 chunk 边界 = 行边界
 *   4. 逐行解析 amount，过滤 amount >= min_amount 的行，输出 NNN,BBBBBB\n（11 字节），流式写
 *   5. 输入/输出各算一份 SHA-256（取前 8 字节 hex），处理完删除两个临时文件
 *
 * Go 的取舍：
 *   - os.File.Read 就是"读进调用方给定的 []byte"，零隐藏缓冲、零额外拷贝 —— 固定内存是天然的
 *   - syscall.Getrusage 直接给出进程 ru_maxrss（真正的峰值，不需要轮询采样）
 *   - 代价：行边界、数字解析、数字格式化全都要手写（没有 split / parseInt / sprintf 可用而不分配）
 *     这里刻意全部手写：为每行创建一个 string 会让"流式"退化成"高 GC 压力的流式"
 */

package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"runtime"
	"syscall"
	"time"
)

const (
	PORT = 8151

	// 确定性数据序列：h(i) = (i+1)*MULT + INC（mod 2^64），amount = (h >> 32) % 100000
	// 用"增量加法"迭代即可：h_{i+1} = h_i + MULT —— 五门语言写法相同，无浮点、无库差异
	MULT = uint64(6364136223846793005)
	INC  = uint64(1442695040888963407)

	LINE_IN  = 10 // "%03d,%05d\n"
	LINE_OUT = 11 // "%03d,%06d\n"（amount*2 可能到 6 位，故输出定长 11）

	GEN_BUF = 64 * 1024 // 生成阶段的写缓冲（同样是固定大小）
)

var (
	DEFAULT_SIZE_MB    = 32
	DEFAULT_CHUNK_KIB  = 64
	DEFAULT_MIN_AMOUNT = 50000
)

type streamRequest struct {
	SizeMb    *int `json:"size_mb"`
	ChunkKib  *int `json:"chunk_kib"`
	MinAmount *int `json:"min_amount"`
}

type streamResponse struct {
	Lang            string  `json:"lang"`
	SizeMb          int     `json:"size_mb"`
	ChunkKib        int     `json:"chunk_kib"`
	MinAmount       int     `json:"min_amount"`
	BytesRead       int64   `json:"bytes_read"`
	LinesRead       int64   `json:"lines_read"`
	BytesWritten    int64   `json:"bytes_written"`
	LinesWritten    int64   `json:"lines_written"`
	OutputFileBytes int64   `json:"output_file_bytes"`
	Checksum        string  `json:"checksum"`
	OutputChecksum  string  `json:"output_checksum"`
	Chunks          int64   `json:"chunks"`
	GenMs           int64   `json:"gen_ms"`
	ProcMs          int64   `json:"proc_ms"`
	ElapsedMs       int64   `json:"elapsed_ms"`
	ThroughputMbS   float64 `json:"throughput_mb_s"`
	RssBeforeBytes  int64   `json:"rss_before_bytes"`
	RssPeakBytes    int64   `json:"rss_peak_bytes"`
	RssDeltaBytes   int64   `json:"rss_delta_bytes"`
	PeakHeapBytes   int64   `json:"peak_heap_bytes"`
	HeapMetric      string  `json:"heap_metric"`
	Cleanup         bool    `json:"cleanup"`
}

// ---- 内存观测 ------------------------------------------------------------
// ru_maxrss 是"进程启动以来的 RSS 峰值"，单位：Linux 为 KB，macOS 为 bytes。
// 用它而不是"当前 RSS"：本场景要证明的是"内存没有被数据撑大"，峰值才是证据。
func rssBytes() int64 {
	var ru syscall.Rusage
	if err := syscall.Getrusage(syscall.RUSAGE_SELF, &ru); err != nil {
		return -1
	}
	if runtime.GOOS == "darwin" {
		return ru.Maxrss
	}
	return ru.Maxrss * 1024
}

// HeapAlloc = 当前存活堆字节（Go 运行时的精确口径，不是采样估计）
func heapBytes() int64 {
	var m runtime.MemStats
	runtime.ReadMemStats(&m)
	return int64(m.HeapAlloc)
}

// ---- 工具：手写定宽数字（不分配任何对象） --------------------------------
func appendFixed(b []byte, v int, width int) []byte {
	pos := len(b)
	for i := 0; i < width; i++ {
		b = append(b, '0')
	}
	for i := width - 1; i >= 0; i-- {
		b[pos+i] = byte('0' + v%10)
		v /= 10
	}
	return b
}

func appendLineIn(b []byte, i int64, amount int) []byte {
	g := int(i % 1000)
	b = append(b, byte('0'+g/100), byte('0'+(g/10)%10), byte('0'+g%10), ',')
	b = appendFixed(b, amount, 5)
	return append(b, '\n')
}

// ---- 阶段一：流式生成源文件（同样是固定缓冲，绝不整体拼进内存） ----------
func generate(path string, lines int64) error {
	f, err := os.Create(path)
	if err != nil {
		return err
	}
	defer f.Close()

	buf := make([]byte, 0, GEN_BUF)
	h := INC
	for i := int64(0); i < lines; i++ {
		h += MULT // uint64 自然环绕
		amount := int((h >> 32) % 100000)
		buf = appendLineIn(buf, i, amount)
		if len(buf)+LINE_IN > cap(buf) {
			if _, err := f.Write(buf); err != nil {
				return err
			}
			buf = buf[:0]
		}
	}
	if len(buf) > 0 {
		if _, err := f.Write(buf); err != nil {
			return err
		}
	}
	return nil
}

// fillChunk 读满整个 buf 或遇到 EOF 返回。返回 (实际字节数, error)。
// Go 的 os.File.Read 不保证读满，所以必须自己循环 —— 这点与 Java 的 readNBytes 不同。
func fillChunk(f *os.File, buf []byte) (int, error) {
	total := 0
	for total < len(buf) {
		n, err := f.Read(buf[total:])
		total += n
		if err == io.EOF {
			return total, nil
		}
		if err != nil {
			return total, err
		}
	}
	return total, nil
}

// ---- 阶段二：流式处理（读 → 解析 → 过滤 → 转换 → 写） -------------------
func process(src, dst string, chunk, minAmount int) (*streamResponse, error) {
	in, err := os.Open(src)
	if err != nil {
		return nil, err
	}
	defer in.Close()
	out, err := os.Create(dst)
	if err != nil {
		return nil, err
	}
	defer out.Close()

	hIn := sha256.New()
	hOut := sha256.New()

	buf := make([]byte, chunk)
	// pending 保存"上一个 chunk 剩下的半行"；容量固定为 chunk+LINE_IN，
	// 因此 append 永远不会触发重新分配 —— 内存占用与文件大小无关。
	pending := make([]byte, 0, chunk+LINE_IN)
	outBuf := make([]byte, 0, chunk+LINE_OUT)

	res := &streamResponse{Lang: "go", ChunkKib: chunk / 1024, MinAmount: minAmount}
	t0 := time.Now()

	flushOut := func() error {
		if len(outBuf) == 0 {
			return nil
		}
		hOut.Write(outBuf)
		if _, err := out.Write(outBuf); err != nil {
			return err
		}
		outBuf = outBuf[:0]
		return nil
	}

	for {
		n, err := fillChunk(in, buf)
		if err != nil {
			return nil, err
		}
		if n == 0 {
			break
		}
		res.Chunks++
		res.BytesRead += int64(n)
		hIn.Write(buf[:n])

		pending = append(pending, buf[:n]...)
		start := 0
		for i := 0; i < len(pending); i++ {
			if pending[i] != '\n' {
				continue
			}
			res.LinesRead++
			if i-start >= LINE_IN-1 {
				// 直接从字节解析 amount（offset 4..8），不构造 string、不 split
				amount := 0
				for k := start + 4; k < start+9; k++ {
					amount = amount*10 + int(pending[k]-'0')
				}
				if amount >= minAmount {
					outBuf = append(outBuf, pending[start:start+4]...) // "%03d," 原样拷贝
					outBuf = appendFixed(outBuf, amount*2, 6)
					outBuf = append(outBuf, '\n')
					res.LinesWritten++
					res.BytesWritten += LINE_OUT
					if len(outBuf)+LINE_OUT > cap(outBuf) {
						if err := flushOut(); err != nil {
							return nil, err
						}
					}
				}
			}
			start = i + 1
		}
		if start > 0 {
			remain := copy(pending, pending[start:])
			pending = pending[:remain]
		}
		if n < len(buf) { // 没读满 = EOF
			break
		}
	}
	if err := flushOut(); err != nil {
		return nil, err
	}

	res.ProcMs = time.Since(t0).Milliseconds()
	res.Checksum = hex.EncodeToString(hIn.Sum(nil)[:8])
	res.OutputChecksum = hex.EncodeToString(hOut.Sum(nil)[:8])
	if secs := time.Since(t0).Seconds(); secs > 0 {
		res.ThroughputMbS = float64(res.BytesRead) / (1024 * 1024) / secs
	}
	res.PeakHeapBytes = heapBytes()
	res.HeapMetric = "go.runtime.MemStats.HeapAlloc"
	return res, nil
}

func handler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "use POST", http.StatusMethodNotAllowed)
		return
	}
	var req streamRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "bad json: "+err.Error(), http.StatusBadRequest)
		return
	}
	sizeMb, chunkKib, minAmount := DEFAULT_SIZE_MB, DEFAULT_CHUNK_KIB, DEFAULT_MIN_AMOUNT
	if req.SizeMb != nil {
		sizeMb = clamp(*req.SizeMb, 1, 512)
	}
	if req.ChunkKib != nil {
		chunkKib = clamp(*req.ChunkKib, 1, 4096)
	}
	if req.MinAmount != nil {
		minAmount = clamp(*req.MinAmount, 0, 99999)
	}

	lines := int64(sizeMb) * 1024 * 1024 / LINE_IN
	tag := fmt.Sprintf("stream16-%d-%d", os.Getpid(), time.Now().UnixNano())
	src := filepath.Join(os.TempDir(), tag+".in")
	dst := filepath.Join(os.TempDir(), tag+".out")

	rssBefore := rssBytes()
	tAll := time.Now()

	if err := generate(src, lines); err != nil {
		http.Error(w, "generate failed: "+err.Error(), http.StatusInternalServerError)
		return
	}
	genMark := time.Since(tAll).Milliseconds()

	res, err := process(src, dst, chunkKib*1024, minAmount)
	if err != nil {
		os.Remove(src)
		os.Remove(dst)
		http.Error(w, "process failed: "+err.Error(), http.StatusInternalServerError)
		return
	}
	elapsed := time.Since(tAll).Milliseconds()

	// 真实写出的字节数（stat 文件，而不是信任计数器）—— 计数器可能与真实写入脱节
	if fi, err := os.Stat(dst); err == nil {
		res.OutputFileBytes = fi.Size()
	}

	// 清理临时文件：不删的话，多跑几次就会把磁盘撑满
	_, e1 := os.Stat(src)
	os.Remove(src)
	os.Remove(dst)
	_, s1 := os.Stat(src)
	_, s2 := os.Stat(dst)
	res.Cleanup = (e1 == nil) && os.IsNotExist(s1) && os.IsNotExist(s2)

	res.SizeMb = sizeMb
	res.GenMs = genMark
	res.ElapsedMs = elapsed
	res.RssBeforeBytes = rssBefore
	res.RssPeakBytes = rssBytes()
	res.RssDeltaBytes = res.RssPeakBytes - res.RssBeforeBytes

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(res)
	log.Printf("stream: size=%dMB chunk=%dKiB lines=%d bytes_out=%d rss_delta=%.1fMiB in %dms",
		sizeMb, chunkKib, res.LinesRead, res.BytesWritten,
		float64(res.RssDeltaBytes)/(1024*1024), res.ElapsedMs)
}

func clamp(v, lo, hi int) int {
	if v < lo {
		return lo
	}
	if v > hi {
		return hi
	}
	return v
}

func main() {
	http.HandleFunc("/stream/process", handler)
	log.Printf("large-file-streaming (go) listening on %d", PORT)
	log.Fatal(http.ListenAndServe(fmt.Sprintf(":%d", PORT), nil))
}
