#!/usr/bin/env python3
# 统一验证器（覆盖全部 5 种语言：Java / Go / Python / Rust / TS-Node）
# 在本机终端运行（沙箱的 Security Center 会拦截删除类操作，本机不会）：
#   python3 .wb_verify/verify_all.py
# 结果写入: .wb_verify/all_results.json 与 .wb_verify/all_results.md
#
# 设计要点（来自多轮验证的经验）:
#  - HTTP 场景: 启动服务 -> 探测端口(任意响应即视为已启动/监听) -> 关闭
#  - 03-cli-tool: 既核对 lines=/words= 数值基准，也核对 -l/-w/-c 的选项语义（防 off-by-one、选项失效类静默错误）
#  - 05-unit-test-mock: 跑各语言测试框架，按退出码 + 测试摘要判定
#  - 12-graceful-shutdown: 启动 -> 先丢一个耗时请求 -> 给"监听进程"发 SIGTERM ->
#                          必须：在途请求正常拿到响应 + 监听释放 + 日志有关闭完成标记 + 无崩溃特征
#  - 13-cpu-bound-parallel: **契约级**断言。验证器用 Python 独立实现同一套 uint64 环绕算法作为
#                          oracle，逐任务比对 checksum —— 位运算语义写错（忘 & MASK / 用 number
#                          而非 BigInt / 有符号输出）在"端口通"的判定下不可能被发现。
#  - 每个 (场景,语言) 用 try/except 包裹，单个失败/超时不影响其余；超时返回 -999
#  - 最后一定写出 JSON/MD 结果（含中断保护）
import os, re, shutil, sys, subprocess, time, signal, json, socket, threading, http.client, urllib.request, urllib.error, traceback

# 路径全部相对本文件推导，不写死绝对路径 —— 仓库目录改名/搬家后脚本仍然可用
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", "scenarios"))
LOGDIR = os.path.join(HERE, "all_logs")
RES_JSON = os.path.join(HERE, "all_results.json")
RES_MD = os.path.join(HERE, "all_results.md")
# 归档目录：每次运行（含过滤运行）都留一份快照，避免全量结果被单场景复跑覆盖
RUNDIR = os.path.join(HERE, "runs")
JAVA17 = "/opt/homebrew/opt/openjdk@17"
# 场景 15 的 Java 用 JDK 21（StructuredTaskScope 是 JDK 21 的 preview API）
JAVA21 = os.path.expanduser("~/.local/share/mise/installs/java/zulu-21")
MISE_SHIMS = os.path.expanduser("~/.local/share/mise/shims")
CARGO_BIN = os.path.expanduser("~/.cargo/bin")
os.makedirs(LOGDIR, exist_ok=True)

ENV = dict(os.environ)
ENV["JAVA_HOME"] = JAVA17
ENV["PATH"] = JAVA17 + "/bin:" + MISE_SHIMS + ":" + CARGO_BIN + ":" + ENV.get("PATH", "")
# 国内网络下 proxy.golang.org / sum.golang.org 不可达，会导致 go mod download 校验超时
ENV["GOPROXY"] = "https://goproxy.cn,direct"
ENV["GOSUMDB"] = "off"
ENV["GOFLAGS"] = "-mod=mod"
ENV["MAVEN_OPTS"] = "-Dmaven.repo.local=" + os.path.expanduser("~/.m2/repository")
# Python 输出重定向到文件时 stdout 默认块缓冲；uvicorn 在优雅关闭后进程会被信号直接终止
# （atexit / 缓冲区 flush 都不会执行），未 flush 的应用日志会整块丢失。强制无缓冲。
ENV["PYTHONUNBUFFERED"] = "1"
# 清掉代理与沙箱注入的端口覆盖变量：
#  - HTTP_PROXY 会让 localhost 请求被代理拦截返回 502（探活假阳性），也会干扰场景 09 的本地调用
#  - SERVER__PORT/SERVER_PORT 会被 Spring Boot 宽松绑定成 server.port，导致 Java 服务绑到错误端口
for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
           "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy",
           "SERVER__PORT", "SERVER_PORT", "SERVER__HOST", "SERVER_HOST", "PORT"):
    ENV.pop(_k, None)


def env_for(name, lang):
    """按场景返回子进程环境（默认全局 ENV）。

    只有场景 15 的 Java 需要特例：它用 JDK 21 的 preview API（StructuredTaskScope），
    用顶层 mise.toml 固定的 JDK 17 编译会直接失败。
    """
    if name == "15-structured-concurrency" and lang == "java":
        e = dict(ENV)
        e["JAVA_HOME"] = JAVA21
        e["PATH"] = JAVA21 + "/bin:" + e.get("PATH", "")
        return e
    return ENV

LANGS = ["java", "go", "python", "rust", "ts-node"]
# 完整端口表(5 种语言)；03=cli, 05=test, 12=graceful
SCENARIOS = [
    {"name":"00-hello-http","kind":"http","ports":{"java":8080,"go":8081,"python":8082,"rust":8083,"ts-node":8084}},
    {"name":"01-json-serialize","kind":"http","ports":{"java":8090,"go":8091,"python":8092,"rust":8093,"ts-node":8094}},
    {"name":"02-concurrent-task","kind":"http","ports":{"java":8085,"go":8086,"python":8087,"rust":8088,"ts-node":8089}},
    {"name":"03-cli-tool","kind":"cli"},
    {"name":"04-file-io","kind":"http","ports":{"java":8095,"go":8096,"python":8097,"rust":8098,"ts-node":8099}},
    {"name":"05-unit-test-mock","kind":"test"},
    {"name":"06-simple-rag-demo","kind":"http","ports":{"java":8100,"go":8101,"python":8102,"rust":8103,"ts-node":8104}},
    {"name":"07-structured-logging","kind":"http","ports":{"java":8105,"go":8106,"python":8107,"rust":8108,"ts-node":8109}},
    {"name":"08-config-management","kind":"http","ports":{"java":8110,"go":8111,"python":8112,"rust":8113,"ts-node":8114}},
    {"name":"09-http-client","kind":"http","ports":{"java":8115,"go":8116,"python":8117,"rust":8118,"ts-node":8119}},
    {"name":"10-rate-limit","kind":"http","ports":{"java":8120,"go":8121,"python":8122,"rust":8123,"ts-node":8124}},
    {"name":"11-db-crud-pool","kind":"http","ports":{"java":8125,"go":8126,"python":8127,"rust":8128,"ts-node":8129}},
    {"name":"12-graceful-shutdown","kind":"graceful","ports":{"java":8130,"go":8131,"python":8132,"rust":8133,"ts-node":8134}},
    # 13+ 为"边界场景"：CPU 密集 / 数据分析 / 结构化并发 / 大文件流式 / 错误处理
    {"name":"13-cpu-bound-parallel","kind":"compute","ports":{"java":8135,"go":8136,"python":8137,"rust":8138,"ts-node":8139}},
    {"name":"14-data-analysis","kind":"data","ports":{"java":8140,"go":8141,"python":8142,"rust":8143,"ts-node":8144}},
    {"name":"15-structured-concurrency","kind":"cancel","ports":{"java":8145,"go":8146,"python":8147,"rust":8148,"ts-node":8149}},
]

PREP_TIMEOUT = {"java":600, "go":1200, "python":600, "rust":1200, "ts-node":600}
RUN_POLL = 120
RUN_TIMEOUT = 120
# 03-cli-tool 的统计基准文件（各语言都以它作为输入）
REPO_README = os.path.normpath(os.path.join(ROOT, "..", "README.md"))
# 12 场景的判定标记：必须出现"关闭完成"正向标记，且不得出现崩溃特征
GRACEFUL_DONE_MARKERS = ("shutdown complete", "shutdown 完成")
GRACEFUL_CRASH_MARKERS = ("traceback", "attributeerror", "panicked", "error[e",
                          "exception in callback", "segmentation fault")

def run(cmd, cwd, log, timeout):
    """返回退出码；超时返回 -999；其它异常返回 -1。"""
    with open(log, "a") as lf:
        lf.write("\n$ " + " ".join(cmd) + "\n")
        lf.flush()  # 必须先刷出去：否则子进程直接写 fd 的输出会跑到"命令回显"前面
        try:
            p = subprocess.run(cmd, cwd=cwd, env=ENV, stdout=lf, stderr=subprocess.STDOUT, timeout=timeout)
            return p.returncode
        except subprocess.TimeoutExpired:
            lf.write("\n[TIMEOUT after %ds]\n" % timeout)
            return -999
        except Exception as e:
            lf.write("\n[RUN ERROR] %s\n" % e)
            return -1

def run_capture(cmd, cwd, log, timeout):
    """同 run()，但把子进程输出**捕获下来返回**（同时写日志）。
    需要解析输出的场景（03 CLI、05 测试摘要）必须用这个：
    直接写同一个 fd 无法保证"命令回显"与"子进程输出"的先后顺序。"""
    with open(log, "a") as lf:
        lf.write("\n$ " + " ".join(cmd) + "\n")
        lf.flush()
        try:
            p = subprocess.run(cmd, cwd=cwd, env=ENV, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, timeout=timeout)
            text = p.stdout.decode("utf-8", "replace")
            lf.write(text)
            lf.flush()
            return p.returncode, text
        except subprocess.TimeoutExpired:
            lf.write("\n[TIMEOUT after %ds]\n" % timeout)
            return -999, ""
        except Exception as e:
            lf.write("\n[RUN ERROR] %s\n" % e)
            return -1, ""

def tail(log, n=25):
    try:
        with open(log) as f:
            return "\n".join(f.read().splitlines()[-n:])
    except Exception:
        return "(no log)"

def prep(lang, kind, d, log):
    if lang == "python" and os.path.exists(os.path.join(d, "requirements.txt")):
        return run(["pip", "install", "-q", "-r", "requirements.txt"], d, log, PREP_TIMEOUT[lang])
    if lang == "go":
        # 测试/运行前先把依赖拉下来(单独计时，避免污染探测窗口)
        return run(["go", "mod", "download"], d, log, PREP_TIMEOUT[lang])
    if lang == "rust":
        return run(["cargo", "build"], d, log, PREP_TIMEOUT[lang])
    if lang == "ts-node":
        return run(["npm", "install"], d, log, PREP_TIMEOUT[lang])
    if lang == "java":
        if kind == "cli":
            return run(["mvn", "-q", "package"], d, log, PREP_TIMEOUT[lang])
        # http/graceful 由 spring-boot:run 在启动时编译，无需单独 prep
        return 0
    return 0

CLI_FILE_REL = "../../../README.md"

def cli_base(lang):
    """03-cli-tool 的命令前缀（不含参数）"""
    if lang == "java": return ["java", "-jar", "target/cli-tool-1.0.0.jar"]
    if lang == "go": return ["go", "run", "."]
    if lang == "rust": return ["cargo", "run", "--"]
    if lang == "ts-node": return ["npx", "tsx", "src/main.ts"]
    if lang == "python": return ["python", "main.py"]
    raise SystemExit("unknown " + lang)

def start_cmd(lang, port, kind, d):
    if kind == "cli":
        return cli_base(lang) + ["-l", "-w", CLI_FILE_REL]
    if kind == "test":
        # 不加 -q：需要 surefire 的 "Tests run: N, Failures: 0" 摘要作为"测试确实跑过"的证据
        if lang == "java": return ["mvn", "test"]
        if lang == "go": return ["go", "test", "./..."]
        if lang == "rust": return ["cargo", "test"]
        if lang == "ts-node": return ["npx", "vitest", "run"]
        if lang == "python": return ["pytest", "-q"]
    # http / graceful / compute / data 共用同一套启动命令（compute/data 只换了判定方式）
    if lang == "java": return ["mvn", "-q", "-DskipTests", "spring-boot:run"]
    if lang == "go": return ["go", "run", "."]
    if lang == "python": return ["bash", "-c", "uvicorn main:app --port %d" % port]
    if lang == "rust": return ["cargo", "run"]
    if lang == "ts-node": return ["npm", "run", "dev"]
    raise SystemExit("unknown " + lang)

def poll_listen(port, timeout):
    """原始 TCP 连接探测端口是否在监听。
    注意：不要用 urllib/curl —— 若环境设置了 HTTP_PROXY，对 localhost 的请求会被
    代理拦截并返回 502，从而把"任意端口"误判为已监听(假阳性)。"""
    end = time.time() + timeout
    while time.time() < end:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=2):
                return True
        except Exception:
            time.sleep(0.5)
    return False

def free_port(port):
    """按端口杀掉残留监听进程, 避免 stale-port 误判。
    只杀"监听方"(-sTCP:LISTEN)：不加这个过滤时，lsof -ti :PORT 会把连到该端口的
    客户端也列出来，脚本自己就可能被自己杀掉。"""
    try:
        out = subprocess.run(["lsof", "-nP", "-iTCP:%d" % port, "-sTCP:LISTEN", "-t"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
        if out:
            for pid in out.split():
                try: os.kill(int(pid), signal.SIGKILL)
                except Exception: pass
    except Exception: pass
    time.sleep(1)

def listener_pid(port):
    """返回当前在 port 上"监听"的进程 PID(优先直接给监听进程发信号)。
    必须带 -sTCP:LISTEN：否则请求方(本脚本自己)也会被列进来，
    若取到自己的 pid 再发 SIGTERM，脚本会把自己杀掉。"""
    try:
        out = subprocess.run(["lsof", "-nP", "-iTCP:%d" % port, "-sTCP:LISTEN", "-t"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
        me = os.getpid()
        for p in out.split():
            if p.strip().isdigit() and int(p) != me: return int(p)
    except Exception: pass
    return None

def kill_tree(proc):
    try: os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except Exception: pass
    try: proc.wait(timeout=10)
    except Exception:
        try: os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception: pass

def verify_http(lang, port, d, log):
    free_port(port)
    with open(log, "a") as lf:
        proc = subprocess.Popen(start_cmd(lang, port, "http", d), cwd=d, env=ENV,
                                 stdout=lf, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        if poll_listen(port, RUN_POLL):
            return True, "listening on %d" % port
        return False, "no response on %d" % port + "\n" + tail(log)
    finally:
        kill_tree(proc)
        subprocess.run(["pkill", "-9", "-f", os.path.join("scenarios", os.path.basename(os.path.dirname(d)))],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)

def port_released(port, timeout):
    """等待端口不再可连接 —— 说明监听进程自己退出了。
    不要用'包装进程是否退出'判断：tsx watch / mvn / go run 这些包装进程会留在原地，
    它们不退出并不代表服务没关干净。"""
    end = time.time() + timeout
    while time.time() < end:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=2):
                time.sleep(0.3)
        except Exception:
            return True
    return False

def hit_long_task(port, result, path="/api/long-task"):
    """发一个耗时约 3s 的请求，把结果写进 result（供"是否等完在途请求"判定）。
    用 http.client 而不是 urllib：前者默认不走代理，避免 HTTP_PROXY 把请求劫持成 502。"""
    t0 = time.time()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
        conn.request("GET", path)
        resp = conn.getresponse()
        body = resp.read().decode("utf-8", "replace")
        result.update(ok=True, status=resp.status, body=body[:160], elapsed=time.time() - t0)
    except Exception as e:
        result.update(ok=False, error=repr(e), elapsed=time.time() - t0)

def verify_graceful(lang, port, d, log):
    free_port(port)
    with open(log, "a") as lf:
        proc = subprocess.Popen(start_cmd(lang, port, "graceful", d), cwd=d, env=ENV,
                                 stdout=lf, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        if not poll_listen(port, RUN_POLL):
            return False, "no response on %d" % port + "\n" + tail(log)
        time.sleep(2)  # 等待运行时完成信号处理器注册
        # 先丢一个耗时请求进去，再发信号 —— 这样能真正验证"是否等 in-flight 请求跑完"
        result = {}
        th = threading.Thread(target=hit_long_task, args=(port, result), daemon=True)
        th.start()
        time.sleep(1.2)
        lp = listener_pid(port)
        if lp:
            try: os.kill(lp, signal.SIGTERM)
            except Exception: pass
        else:
            try: os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except Exception: pass
        released = port_released(port, 25)
        th.join(timeout=15)
        time.sleep(0.5)  # 给日志一点落盘时间
        low = open(log).read().lower()
        # 注意：不要用 'shutdown' 这种宽泛词做判定 —— 日志里的场景路径本身含
        # '12-graceful-shutdown'，任何输出（哪怕异常栈）都会命中，必然假阳性。
        has_done = any(m in low for m in GRACEFUL_DONE_MARKERS)
        crash = [m for m in GRACEFUL_CRASH_MARKERS if m in low]
        reasons = []
        if not released:
            reasons.append("SIGTERM 后 25s 仍在监听（未真正关闭）")
        if not has_done:
            reasons.append("日志缺少关闭完成标记")
        if not result.get("ok"):
            reasons.append("在途请求被打断（%s）" % result.get("error", "无响应"))
        if crash:
            reasons.append("出现崩溃特征: %s" % ",".join(crash))
        ok = not reasons
        if ok:
            note = ("优雅关闭完成：在途请求 HTTP %s 耗时 %.2fs 未被切断；监听已释放（%.2fs）；关闭日志齐全"
                    % (result.get("status"), result.get("elapsed", 0), released))
        else:
            note = "; ".join(reasons)
        return ok, note
    finally:
        # 清掉可能滞留的包装进程（npm/mvn/go run），但判定已在上面完成
        try: os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception: pass
        subprocess.run(["pkill", "-9", "-f", os.path.join("scenarios", os.path.basename(os.path.dirname(d)))],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)

# ---------------- 契约级断言（compute 类：13-cpu-bound-parallel 起） ----------------
# 思路：验证器用 Python **独立实现**一遍任务体算法作为 oracle，
# 再把各语言返回的 checksum 与之逐位比对 —— 不需要跨语言聚合，
# 每个语言都能独立判定，且能精确指出是哪个任务的哪一位不一致。
COMPUTE_SPEC = {"task_count": 4, "iterations": 300000, "concurrency": 2}

_U64_MASK = (1 << 64) - 1


def oracle_state(task_id, iterations):
    """任务体算法的 Python 独立实现（uint64 环绕 LCG）。"""
    state = (task_id + 1) & _U64_MASK
    for _ in range(iterations):
        state = (state * 6364136223846793005 + 1442695040888963407) & _U64_MASK
    return state


def oracle_expected(spec):
    """返回 (逐任务期望 checksum 列表, 期望总 checksum)。"""
    checks = [oracle_state(i, spec["iterations"]) for i in range(spec["task_count"])]
    return checks, sum(checks) & _U64_MASK


def http_json_post(port, path, payload, timeout=300):
    """POST JSON，返回 (status, parsed)。
    用 http.client 而非 urllib：前者默认不走系统代理，
    避免 HTTP_PROXY 把 localhost 请求劫持成 502（见文件头 §7.1）。"""
    body = json.dumps(payload).encode("utf-8")
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.request("POST", path, body=body, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8", "replace")
        try:
            return resp.status, json.loads(raw)
        except Exception:
            return resp.status, {"_raw": raw[:400]}
    finally:
        try:
            conn.close()
        except Exception:
            pass


def verify_compute(lang, port, d, log):
    """场景 13 契约级断言：不只看"端口通了"，而是逐字段核对响应内容。

    为什么必须做契约级而不是端口探活：
      本场景的"行为"就是 checksum。若某门语言的整数语义写错
      （Python 忘记 & MASK、TS 用 number 而非 BigInt、Java 用有符号输出），
      服务照样能起来、端口照样通 —— 只有比对 checksum 才能发现。
    """
    free_port(port)
    with open(log, "a") as lf:
        proc = subprocess.Popen(start_cmd(lang, port, "compute", d), cwd=d, env=ENV,
                                stdout=lf, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        if not poll_listen(port, RUN_POLL):
            return False, "no response on %d" % port + "\n" + tail(log)

        want_checks, want_total = oracle_expected(COMPUTE_SPEC)

        t0 = time.time()
        try:
            status, body = http_json_post(port, "/compute", COMPUTE_SPEC)
        except Exception as e:
            return False, "请求 /compute 失败: %r\n%s" % (e, tail(log))
        elapsed = time.time() - t0

        if status != 200:
            return False, "HTTP %s（期望 200）: %s" % (status, str(body)[:200])

        # 回显字段必须与请求一致。
        # 注意：请求字段名与响应字段名不同名（task_count → total_tasks），必须逐项映射，
        # 不能拿请求的 key 直接去索引响应。
        for field, want in (("total_tasks", COMPUTE_SPEC["task_count"]),
                            ("iterations", COMPUTE_SPEC["iterations"]),
                            ("concurrency", COMPUTE_SPEC["concurrency"])):
            if body.get(field) != want:
                return False, "%s 回显不符: 期望 %s，实际 %s" % (field, want, body.get(field))

        results = body.get("results")
        if not isinstance(results, list) or len(results) != COMPUTE_SPEC["task_count"]:
            return False, "results 长度不符: %s" % (
                len(results) if isinstance(results, list) else repr(results)[:120])

        for i, r in enumerate(results):
            if r.get("id") != i:
                return False, "results[%d].id=%s（期望 %d，须按 id 升序）" % (i, r.get("id"), i)
            got = str(r.get("checksum"))
            if got != str(want_checks[i]):
                return False, ("task %d checksum 与 oracle 不一致: 实际 %s / 期望 %s"
                               % (i, got, want_checks[i]))

        if str(body.get("checksum")) != str(want_total):
            return False, ("总 checksum 与 oracle 不一致: 实际 %s / 期望 %s"
                           % (body.get("checksum"), want_total))

        return True, ("契约一致：%d 个任务 checksum 与 oracle 逐一相符，总和=%s；"
                      "本轮耗时 %.1fs（iterations=%d, concurrency=%d）"
                      % (COMPUTE_SPEC["task_count"], want_total, elapsed,
                         COMPUTE_SPEC["iterations"], COMPUTE_SPEC["concurrency"]))
    finally:
        kill_tree(proc)
        subprocess.run(["pkill", "-9", "-f", os.path.join("scenarios", os.path.basename(os.path.dirname(d)))],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)


# ---- 场景 14：数据分析处理 ----
DATA_SPEC = {"rows": 200000, "categories": 8}

_DATA_MULT = 6364136223846793005
_DATA_INC = 1442695040888963407

# oracle 全量重算一次约 1~2 秒（20 万行大整数运算 + 排序），缓存避免五门语言重复算
_data_oracle_cache = None


def _data_amount_of(i):
    h = ((i + 1) * _DATA_MULT + _DATA_INC) & _U64_MASK
    return (h >> 32) % 100000


def oracle_data(spec):
    """场景 14 的 Python 独立 oracle：完整重算期望的分组统计与 Top10。

    分位数口径：nearest-rank（排序后取 ceil(p*n/100)-1 下标，整数运算无浮点歧义）。
    """
    global _data_oracle_cache
    if _data_oracle_cache is not None:
        return _data_oracle_cache

    rows, cats = spec["rows"], spec["categories"]
    amounts = [_data_amount_of(i) for i in range(rows)]
    buckets = [[] for _ in range(cats)]
    sums = [0] * cats
    for i in range(rows):
        c = i % cats
        buckets[c].append(amounts[i])
        sums[c] += amounts[i]

    groups = []
    for c in range(cats):
        vals = sorted(buckets[c])
        n = len(vals)
        if n == 0:
            continue
        # ceil(p*n/100) 的整数实现：先 +99 再整除
        i50 = max(0, min(n - 1, (50 * n + 99) // 100 - 1))
        i95 = max(0, min(n - 1, (95 * n + 99) // 100 - 1))
        groups.append({
            "category": "cat-%d" % c, "count": n, "sum": sums[c],
            "avg": sums[c] / n, "p50": vals[i50], "p95": vals[i95],
        })

    order = sorted(range(rows), key=lambda i: (-amounts[i], i))
    top10 = [{"id": i, "category": "cat-%d" % (i % cats), "amount": amounts[i]}
             for i in order[:10]]

    _data_oracle_cache = (groups, top10)
    return _data_oracle_cache


def _close(a, b, tol=1e-9):
    return isinstance(a, (int, float)) and isinstance(b, (int, float)) \
        and abs(a - b) <= tol * max(1.0, abs(a), abs(b))


def verify_data(lang, port, d, log):
    """场景 14 契约级断言：分组统计 / Top10 与 Python oracle 逐字段比对。

    本场景的"行为"就是聚合结果。若某门语言的整数语义写错（uint64 环绕、
    分位数口径、Top-K 平局规则），服务照样能起 —— 只有比对聚合结果才能发现。
    """
    free_port(port)
    with open(log, "a") as lf:
        proc = subprocess.Popen(start_cmd(lang, port, "data", d), cwd=d, env=ENV,
                                stdout=lf, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        if not poll_listen(port, RUN_POLL):
            return False, "no response on %d" % port + "\n" + tail(log)

        want_groups, want_top = oracle_data(DATA_SPEC)

        t0 = time.time()
        try:
            status, body = http_json_post(port, "/analyze", DATA_SPEC, timeout=600)
        except Exception as e:
            return False, "请求 /analyze 失败: %r\n%s" % (e, tail(log))
        elapsed = time.time() - t0

        if status != 200:
            return False, "HTTP %s（期望 200）: %s" % (status, str(body)[:300])

        if body.get("rows") != DATA_SPEC["rows"] or body.get("categories") != DATA_SPEC["categories"]:
            return False, "rows/categories 回显不符: %r/%r" % (body.get("rows"), body.get("categories"))

        # 分组统计
        groups = body.get("groups")
        if not isinstance(groups, list) or len(groups) != len(want_groups):
            return False, "groups 数量不符: %s（期望 %d）" % (
                len(groups) if isinstance(groups, list) else repr(groups)[:120],
                len(want_groups))
        for i, (g, w) in enumerate(zip(groups, want_groups)):
            if g.get("category") != w["category"]:
                return False, "groups[%d].category=%r（期望 %r，须按名称升序）" % (
                    i, g.get("category"), w["category"])
            for k in ("count", "sum", "p50", "p95"):
                if g.get(k) != w[k]:
                    return False, "groups[%d].%s=%r 与 oracle 不一致（期望 %r）" % (
                        i, k, g.get(k), w[k])
            if not _close(g.get("avg"), w["avg"]):
                return False, "groups[%d].avg=%r 与 oracle 不一致（期望 %r）" % (
                    i, g.get("avg"), w["avg"])

        # Top-10
        top10 = body.get("top10")
        if not isinstance(top10, list) or len(top10) != len(want_top):
            return False, "top10 数量不符: %s" % (
                len(top10) if isinstance(top10, list) else repr(top10)[:120])
        for i, (t, w) in enumerate(zip(top10, want_top)):
            for k in ("id", "category", "amount"):
                if t.get(k) != w[k]:
                    return False, "top10[%d].%s=%r 与 oracle 不一致（期望 %r）" % (
                        i, k, t.get(k), w[k])

        # 耗时字段仅要求存在且非负（跨机器不可比，不做强断言）
        for k in ("gen_ms", "agg_ms", "elapsed_ms"):
            if not isinstance(body.get(k), (int, float)) or body[k] < 0:
                return False, "%s 字段缺失或非法: %r" % (k, body.get(k))

        return True, ("契约一致：%d 组统计 + Top10 与 oracle 逐字段相符；"
                      "服务端耗时 %sms（含生成+聚合），验证请求 %.1fs"
                      % (len(groups), body.get("elapsed_ms"), elapsed))
    finally:
        kill_tree(proc)
        subprocess.run(["pkill", "-9", "-f", os.path.join("scenarios", os.path.basename(os.path.dirname(d)))],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)


# ---- 场景 15：结构化并发 + 取消传播 ----
# 三个用例覆盖"取消传播"的三条语义：
#   1) 全成功     —— 作用域正常收尾，所有子任务 completed
#   2) fail-fast  —— 一个子任务失败，兄弟任务必须被取消（elapsed 远小于 task_ms）
#   3) 父超时     —— deadline 到期，全部子任务取消
# 最后是**延迟检查**：请求返回后再等一段时间（> task_ms 的量级），GET /stats 的
# active_tasks 必须为 0 —— 这条能抓出"只是标记取消、任务其实还在后台跑完"的假实现。
# 为什么必须这么做：五门语言都能让服务起来、都能返回 200；
# 只有"取消是否真的传播 + 作用域是否真的收尾"是本场景的业务语义。
CANCEL_CASES = [
    {
        "name": "全成功",
        "spec": {"tasks": 4, "task_ms": 200, "fail_index": -1, "fail_after_ms": 0, "timeout_ms": 0},
        "want": {"outcome": "completed", "completed": [0, 1, 2, 3], "cancelled": [], "failed": -1},
        "min_elapsed_ms": 150,
    },
    {
        "name": "fail-fast 取消传播",
        "spec": {"tasks": 8, "task_ms": 2000, "fail_index": 3, "fail_after_ms": 250, "timeout_ms": 0},
        "want": {"outcome": "failed", "completed": [], "cancelled": [0, 1, 2, 4, 5, 6, 7], "failed": 3},
        "max_elapsed_ms": 1500,
    },
    {
        "name": "父作用域超时",
        "spec": {"tasks": 6, "task_ms": 2000, "fail_index": -1, "fail_after_ms": 0, "timeout_ms": 300},
        "want": {"outcome": "timeout", "completed": [], "cancelled": [0, 1, 2, 3, 4, 5], "failed": -1},
        "max_elapsed_ms": 1500,
    },
]
# 子任务"本该跑完"的时间量级：请求返回后仍不许有存活子任务
CANCEL_SETTLE_SLEEP = 3.0


def http_json_get(port, path, timeout=30):
    """GET JSON，返回 (status, parsed)。同样用 http.client 避免代理劫持。"""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8", "replace")
        try:
            return resp.status, json.loads(raw)
        except Exception:
            return resp.status, {"_raw": raw[:400]}
    finally:
        try:
            conn.close()
        except Exception:
            pass


def verify_cancel(lang, port, d, log, env):
    """场景 15 契约级断言：取消传播 + 作用域收尾。

    注意 outcome/completed/cancelled/failed 是"语义字段"，必须逐项比对：
    若某门语言的取消没传播（兄弟任务照常跑满），outcome 仍可能是 failed，
    但 completed 会非空、elapsed 会接近 task_ms —— 时间断言就是用来抓这个的。
    """
    free_port(port)
    with open(log, "a") as lf:
        proc = subprocess.Popen(start_cmd(lang, port, "cancel", d), cwd=d, env=env,
                                stdout=lf, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        if not poll_listen(port, RUN_POLL):
            return False, "no response on %d" % port + "\n" + tail(log)

        notes = []
        for case in CANCEL_CASES:
            spec, want = case["spec"], case["want"]
            try:
                status, body = http_json_post(port, "/fanout", spec, timeout=120)
            except Exception as e:
                return False, "[%s] 请求 /fanout 失败: %r\n%s" % (case["name"], e, tail(log))
            if status != 200:
                return False, "[%s] HTTP %s（期望 200）: %s" % (case["name"], status, str(body)[:300])

            for f in ("tasks", "task_ms", "fail_index", "timeout_ms"):
                if body.get(f) != spec[f]:
                    return False, "[%s] %s 回显不符: %r（期望 %r）" % (case["name"], f, body.get(f), spec[f])
            for f in ("outcome", "completed", "cancelled", "failed"):
                if body.get(f) != want[f]:
                    return False, "[%s] %s=%r 与契约不符（期望 %r）" % (
                        case["name"], f, body.get(f), want[f])
            if body.get("leaked") != 0:
                return False, "[%s] leaked=%r（结构化保证：作用域退出时不应有存活子任务）" % (
                    case["name"], body.get("leaked"))

            ems = body.get("elapsed_ms")
            if not isinstance(ems, (int, float)):
                return False, "[%s] elapsed_ms 字段缺失或非法: %r" % (case["name"], ems)
            if "max_elapsed_ms" in case and ems > case["max_elapsed_ms"]:
                return False, ("[%s] elapsed_ms=%s 超过上限 %s —— 取消未真正传播"
                               "（兄弟任务仍在跑满 task_ms=%s）"
                               % (case["name"], ems, case["max_elapsed_ms"], spec["task_ms"]))
            if "min_elapsed_ms" in case and ems < case["min_elapsed_ms"]:
                return False, "[%s] elapsed_ms=%s 低于下限 %s —— 子任务疑似没真正等待" % (
                    case["name"], ems, case["min_elapsed_ms"])
            notes.append("%s outcome=%s %sms" % (case["name"], body.get("outcome"), ems))

        # 延迟检查：取消"真的生效"还是"只是标记" —— 看有没有僵尸子任务
        time.sleep(CANCEL_SETTLE_SLEEP)
        try:
            status, st = http_json_get(port, "/stats", timeout=30)
        except Exception as e:
            return False, "GET /stats 失败: %r" % (e,)
        if status != 200:
            return False, "GET /stats HTTP %s（期望 200）" % status
        if st.get("active_tasks") != 0:
            return False, ("请求返回 %.1fs 后 active_tasks=%r —— 子任务并未真正结束（取消只是标记）"
                           % (CANCEL_SETTLE_SLEEP, st.get("active_tasks")))

        return True, ("取消传播契约一致：%s；返回 %.1fs 后 active_tasks=0（子任务确已终止），"
                      "累计 started=%s / completed=%s / cancelled=%s"
                      % (" ｜ ".join(notes), CANCEL_SETTLE_SLEEP,
                         st.get("started"), st.get("completed"), st.get("cancelled")))
    finally:
        kill_tree(proc)
        subprocess.run(["pkill", "-9", "-f", os.path.join("scenarios", os.path.basename(os.path.dirname(d)))],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)


def expected_cli_counts(path):
    """基准统计口径（与 Scala/Python/Rust/Java/Go 一致的"逻辑行数"）：
    行数 = 换行符个数，末行无换行时再 +1；词数 = 按空白切分。
    对以换行结尾的 README.md，行数恰好等于 wc -l 的结果。"""
    with open(path, encoding="utf-8") as f:
        content = f.read()
    if content == "":
        return 0, 0
    lines = content.count("\n") + (0 if content.endswith("\n") else 1)
    return lines, len(content.split())

def parse_metrics(text):
    return dict((k, int(v)) for k, v in re.findall(r"(lines|words|chars)=(\d+)", text))

def verify_cli(lang, d, log):
    """两层校验：
    1) 数值正确性：lines/words 与独立计算的基准一致（不只看有没有 'lines='）
    2) 选项语义：-l / -w / -c 必须各自"只输出对应指标"，不传选项才全量输出
       —— 曾经 TS-Node 把选项读成 options.l（实际是 options.lines），三个选项全部失效却照样"有输出"
    """
    want_l, want_w = expected_cli_counts(REPO_README)

    rc, out = run_capture(cli_base(lang) + ["-l", "-w", CLI_FILE_REL], d, log, RUN_TIMEOUT)
    if rc != 0: return False, "exit=%d" % rc
    got = parse_metrics(out)
    if (got.get("lines"), got.get("words")) != (want_l, want_w):
        return False, ("统计值与基准不一致: 工具 lines=%s words=%s / 基准 lines=%d words=%d"
                       % (got.get("lines"), got.get("words"), want_l, want_w))
    if set(got) != {"lines", "words"}:
        return False, "-l -w 应只输出 lines/words，实际输出 %s" % ",".join(sorted(got))

    # 单选项语义 + 数值
    for flag, key, want in (("-l", "lines", want_l), ("-w", "words", want_w)):
        rc, out = run_capture(cli_base(lang) + [flag, CLI_FILE_REL], d, log, RUN_TIMEOUT)
        if rc != 0: return False, "%s exit=%d" % (flag, rc)
        got = parse_metrics(out)
        if set(got) != {key}:
            return False, "%s 应只输出 %s=，实际输出 %s" % (flag, key, ",".join(sorted(got)) or "空")
        if got[key] != want:
            return False, "%s 值不符: %s=%d / 基准 %d" % (flag, key, got[key], want)
    rc, out = run_capture(cli_base(lang) + ["-c", CLI_FILE_REL], d, log, RUN_TIMEOUT)
    if rc != 0: return False, "-c exit=%d" % rc
    got_c = parse_metrics(out)
    if set(got_c) != {"chars"}:
        return False, "-c 应只输出 chars=，实际输出 %s" % (",".join(sorted(got_c)) or "空")
    # chars 口径：Java 按 UTF-16 单元、其余按 Unicode 码点（README 已注明该差异），故只做下界校验
    cp = len(open(REPO_README, encoding="utf-8").read())
    if got_c["chars"] < cp:
        return False, "chars=%d 小于码点数 %d" % (got_c["chars"], cp)

    # 不带选项 → 三项全输出
    rc, out = run_capture(cli_base(lang) + [CLI_FILE_REL], d, log, RUN_TIMEOUT)
    if rc != 0: return False, "无选项 exit=%d" % rc
    got_all = parse_metrics(out)
    if set(got_all) != {"lines", "words", "chars"}:
        return False, "无选项时应输出三项，实际 %s" % (",".join(sorted(got_all)) or "空")
    return True, ("lines=%d words=%d 与基准一致；-l/-w/-c 单选项语义正确；chars=%d"
                  % (want_l, want_w, got_c["chars"]))

def verify_test(lang, d, log):
    rc, out = run_capture(start_cmd(lang, 0, "test", d), d, log, PREP_TIMEOUT[lang])
    if rc == -999: return False, "超时(timeout)"
    low = out.lower()
    # 失败信号：非 0 退出码、FAIL、明确的失败计数、构建失败
    if rc != 0:
        return False, "exit=%d\n%s" % (rc, tail(log))
    if re.search(r"failures:\s*[1-9]", low):
        return False, "存在失败用例\n%s" % tail(log)
    if re.search(r"errors:\s*[1-9]", low) or "build failure" in low:
        return False, "存在错误/构建失败\n%s" % tail(log)
    # 正向证据：必须真的看到测试被跑过（返回摘要），而不是"什么都没跑还退 0"
    ev = extract_test_evidence(lang, out)
    if ev is None:
        return False, "未捕获到测试摘要，无法证明测试确实执行\n" + tail(log)
    return True, "tests passed (%s)" % ev

def extract_test_evidence(lang, out):
    """从日志里抽取"测试确实跑过且通过"的证据字符串；取不到返回 None。"""
    if lang == "java":
        m = re.search(r"Tests run:\s*(\d+),\s*Failures:\s*(\d+),\s*Errors:\s*(\d+),\s*Skipped:\s*(\d+)", out)
        if m:
            return "Tests run %s, Failures %s, Errors %s" % (m.group(1), m.group(2), m.group(3))
        return None
    if lang == "python":
        m = re.search(r"(\d+) passed", out)
        return "%s passed" % m.group(1) if m else None
    if lang == "ts-node":
        m = re.search(r"Tests\s+(\d+) passed", out)
        return "%s passed" % m.group(1) if m else None
    if lang == "rust":
        m = re.search(r"test result: ok\.\s*(\d+) passed;\s*(\d+) failed", out)
        return "%s passed, %s failed" % (m.group(1), m.group(2)) if m else None
    if lang == "go":
        return "go test ./... ok" if re.search(r"^ok\s+\S+", out, re.M) else None
    return None

def main():
    subprocess.run(["pkill", "-9", "-f", "scenarios"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    # 可选参数: 只跑指定场景前缀, 例如 python3 verify_all.py 02 05 06 07 08 09
    filters = sys.argv[1:]
    scen_list = SCENARIOS
    if filters:
        scen_list = [s for s in SCENARIOS if any(s["name"].startswith(f) or s["name"] == f for f in filters)]
        if not scen_list:
            print("无匹配场景:", filters); return
    results = []
    try:
        for sc in scen_list:
            name = sc["name"]; kind = sc["kind"]
            print("########## %s (%s) ##########" % (name, kind), flush=True)
            rec = {"scenario": name, "kind": kind, "langs": {}}
            for lang in LANGS:
                d = os.path.join(ROOT, name, lang)
                if not os.path.isdir(d):
                    rec["langs"][lang] = {"status": "SKIP", "note": "无该语言目录"}
                    print("  [%s] SKIP (无目录)" % lang, flush=True)
                    continue
                log = os.path.join(LOGDIR, "%s_%s.log" % (name, lang))
                open(log, "w").close()
                try:
                    rc = prep(lang, kind, d, log)
                    if rc != 0:
                        note = "依赖/编译失败 rc=%d" % rc + (" (超时)" if rc == -999 else "")
                        rec["langs"][lang] = {"status": "PREP_FAIL", "note": note, "log": tail(log)}
                        print("  [%s] PREP_FAIL rc=%d" % (lang, rc), flush=True)
                        continue
                    if kind == "http":
                        ok, note = verify_http(lang, sc["ports"][lang], d, log)
                    elif kind == "cli":
                        ok, note = verify_cli(lang, d, log)
                    elif kind == "test":
                        ok, note = verify_test(lang, d, log)
                    elif kind == "graceful":
                        ok, note = verify_graceful(lang, sc["ports"][lang], d, log)
                    elif kind == "compute":
                        ok, note = verify_compute(lang, sc["ports"][lang], d, log)
                    elif kind == "data":
                        ok, note = verify_data(lang, sc["ports"][lang], d, log)
                    elif kind == "cancel":
                        ok, note = verify_cancel(lang, sc["ports"][lang], d, log, env_for(name, lang))
                    else:
                        ok, note = False, "unknown kind"
                    st = "PASS" if ok else "FAIL"
                    rec["langs"][lang] = {"status": st, "note": note}
                    print("  [%s] %s" % (lang, st), flush=True)
                    if not ok:
                        print("     " + note.splitlines()[0], flush=True)
                except Exception as e:
                    rec["langs"][lang] = {"status": "ERROR", "note": "exception: %s" % e, "log": tail(log)}
                    print("  [%s] ERROR %s" % (lang, e), flush=True)
            results.append(rec)
    finally:
        # 无论如何都写出结果(避免单点崩溃导致无产出)
        try:
            tag = "full" if not filters else "sub-" + "_".join(filters)
            tp = sum(1 for r in results for l, v in r["langs"].items() if v["status"] == "PASS")
            tf = sum(1 for r in results for l, v in r["langs"].items() if v["status"] == "FAIL")
            te = sum(1 for r in results for l, v in r["langs"].items() if v["status"] == "ERROR")
            tprep = sum(1 for r in results for l, v in r["langs"].items() if v["status"] == "PREP_FAIL")
            tskip = sum(1 for r in results for l, v in r["langs"].items() if v["status"] == "SKIP")
            with open(RES_JSON, "w") as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            with open(RES_MD, "w") as f:
                f.write("# 验证结果（%s ｜ %d 个场景 × %d 种语言 ｜ %s）\n\n"
                        % (tag, len(results), len(LANGS), time.strftime("%Y-%m-%d %H:%M:%S")))
                f.write("**SUMMARY** PASS=%d ｜ FAIL=%d ｜ PREP_FAIL=%d ｜ ERROR=%d ｜ SKIP=%d\n\n"
                        % (tp, tf, tprep, te, tskip))
                for rec in results:
                    f.write("## %s (%s)\n" % (rec["scenario"], rec["kind"]))
                    for lang, v in rec["langs"].items():
                        f.write("- %s: **%s** — %s\n" % (lang, v["status"], v.get("note", "")))
                    f.write("\n")
            # 归档快照：过滤运行会覆盖 all_results.*，归档保留每次运行的独立记录
            os.makedirs(RUNDIR, exist_ok=True)
            stamp = time.strftime("%Y%m%d-%H%M%S") + "_" + tag
            shutil.copyfile(RES_JSON, os.path.join(RUNDIR, stamp + ".json"))
            shutil.copyfile(RES_MD, os.path.join(RUNDIR, stamp + ".md"))
            print("==== SUMMARY PASS=%d FAIL=%d PREP_FAIL=%d ERROR=%d SKIP=%d ====" % (tp, tf, tprep, te, tskip), flush=True)
            print("结果已写入: %s 与 %s" % (RES_JSON, RES_MD), flush=True)
            print("本次运行已归档: %s/%s.{json,md}" % (RUNDIR, stamp), flush=True)
        except Exception:
            traceback.print_exc()

if __name__ == "__main__":
    main()
