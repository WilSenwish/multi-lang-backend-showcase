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
import os, re, shutil, sys, subprocess, time, signal, json, socket, threading, http.client, urllib.request, urllib.error, traceback, hashlib, tempfile, math

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
    {"name":"00-hello-http","kind":"contract","ports":{"java":8080,"go":8081,"python":8082,"rust":8083,"ts-node":8084}},
    {"name":"01-json-serialize","kind":"contract","ports":{"java":8090,"go":8091,"python":8092,"rust":8093,"ts-node":8094}},
    {"name":"02-concurrent-task","kind":"contract","ports":{"java":8085,"go":8086,"python":8087,"rust":8088,"ts-node":8089}},
    {"name":"03-cli-tool","kind":"cli"},
    {"name":"04-file-io","kind":"contract","ports":{"java":8095,"go":8096,"python":8097,"rust":8098,"ts-node":8099}},
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
    {"name":"16-large-file-streaming","kind":"stream","ports":{"java":8150,"go":8151,"python":8152,"rust":8153,"ts-node":8154}},
    {"name":"17-error-handling","kind":"error","ports":{"java":8155,"go":8156,"python":8157,"rust":8158,"ts-node":8159}},
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


def http_json_get(port, path, timeout=30, headers=None):
    """GET JSON，返回 (status, parsed)。同样用 http.client 避免代理劫持。
    headers 用于场景 17 的 X-Trace-Id 回显断言。"""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.request("GET", path, headers=headers or {})
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


# ---- 场景 16：大文件流式处理 ----
# 三个用例覆盖"流式"的三条语义：
#   1) 8MB / 1KiB 块  —— 8192 个块，行几乎必然跨块边界；证明"残余行拼接"正确
#   2) 8MB / 64KiB 块 —— 同一份数据换个块大小，摘要必须完全一致（与缓冲大小无关）
#   3) 32MB / 64KiB   —— 数据量 4 倍，但 RSS 增量不得超过上限（是否真的没往内存里塞）
# 为什么必须这么做：五门语言都能让服务起来、都能返回 200；
# "是否流式"在响应码上完全看不出来，只有「摘要逐字节一致 + 内存增量有上限」能证明。
STREAM_LINE_IN = 10    # "%03d,%05d\n"
STREAM_LINE_OUT = 11   # "%03d,%06d\n"
STREAM_CASES = [
    {"name": "8MB/1KiB 块", "spec": {"size_mb": 8, "chunk_kib": 1, "min_amount": 50000}},
    {"name": "8MB/64KiB 块", "spec": {"size_mb": 8, "chunk_kib": 64, "min_amount": 50000}},
    {"name": "32MB/64KiB 块", "spec": {"size_mb": 32, "chunk_kib": 64, "min_amount": 50000},
     "mem_cap_bytes": 16 * 1024 * 1024},
]

_stream_cache = {}
_STREAM_PREFIX = [b"%03d," % g for g in range(1000)]       # 行首 "NNN," 只有 1000 种
_STREAM_AMOUNT = [b"%05d" % a for a in range(100000)]      # amount 只有 100000 种
_STREAM_NL = b"\n"


def oracle_stream(sizes_mb, min_amount):
    """场景 16 的 Python 独立 oracle：一次遍历算到 max(sizes_mb)，沿途记录各 size 的摘要。

    为什么能"一次遍历算多个"：第 i 行只依赖 i，所以 8MB 的输入恰好是 32MB 输入的前缀，
    在行边界处 flush 缓冲并 copy() 一份 hash 状态即可，不必重复生成 3 遍。
    """
    sizes_mb = sorted(set(sizes_mb))
    max_mb = sizes_mb[-1]
    key = (max_mb, min_amount)
    if key in _stream_cache:
        got = _stream_cache[key]
        if all(s in got for s in sizes_mb):
            return {s: got[s] for s in sizes_mb}

    lines_total = (max_mb << 20) // STREAM_LINE_IN
    # 边界：处理完第 N 行时的快照（升序）
    bounds = {}
    for s in sizes_mb:
        bounds[(s << 20) // STREAM_LINE_IN] = s

    h_in = hashlib.sha256()
    h_out = hashlib.sha256()
    in_buf, out_buf = [], []
    out_bytes = 0
    h = _DATA_INC  # 与场景 14 同款序列：h(i) = (i+1)*MULT + INC
    results = {}

    def flush():
        if in_buf:
            h_in.update(b"".join(in_buf))
            in_buf.clear()
        if out_buf:
            blk = b"".join(out_buf)
            h_out.update(blk)
            out_buf.clear()
            return len(blk)
        return 0

    carried = 0
    for i in range(lines_total):
        h = (h + _DATA_MULT) & _U64_MASK
        a = (h >> 32) % 100000
        p = _STREAM_PREFIX[i % 1000]
        in_buf.append(p)
        in_buf.append(_STREAM_AMOUNT[a])
        in_buf.append(_STREAM_NL)
        if a >= min_amount:
            out_buf.append(p)
            out_buf.append(b"%06d" % (a * 2))
            out_buf.append(_STREAM_NL)
        if len(in_buf) >= 3 * 65536 or len(out_buf) >= 3 * 65536:
            carried += flush()
        n = i + 1
        if n in bounds:
            carried += flush()
            results[bounds[n]] = {
                "lines_read": n,
                "bytes_read": n * STREAM_LINE_IN,
                "lines_written": carried // STREAM_LINE_OUT,  # 输出行定长 11 字节
                "bytes_written": carried,
                "checksum": h_in.copy().hexdigest()[:16],
                "output_checksum": h_out.copy().hexdigest()[:16],
            }
    carried += flush()
    results[bounds[lines_total]] = {
        "lines_read": lines_total,
        "bytes_read": lines_total * STREAM_LINE_IN,
        "lines_written": carried // STREAM_LINE_OUT,
        "bytes_written": carried,
        "checksum": h_in.hexdigest()[:16],
        "output_checksum": h_out.hexdigest()[:16],
    }
    _stream_cache[key] = results
    return {s: results[s] for s in sizes_mb}


def verify_stream(lang, port, d, log):
    """场景 16 契约级断言：逐字节摘要 + 块数 + 内存增量上限。

    本场景的"行为"就是"用固定内存把大文件处理完"。若某门语言退化成一次性读入，
    服务照样返回 200、摘要照样正确 —— 只有 rss_delta_bytes 会随数据量线性增长。
    """
    free_port(port)
    with open(log, "a") as lf:
        proc = subprocess.Popen(start_cmd(lang, port, "stream", d), cwd=d, env=ENV,
                                stdout=lf, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        if not poll_listen(port, RUN_POLL):
            return False, "no response on %d" % port + "\n" + tail(log)

        sizes = [c["spec"]["size_mb"] for c in STREAM_CASES]
        wants = oracle_stream(sizes, STREAM_CASES[0]["spec"]["min_amount"])

        notes = []
        for case in STREAM_CASES:
            spec, want = case["spec"], wants[case["spec"]["size_mb"]]
            try:
                status, body = http_json_post(port, "/stream/process", spec, timeout=600)
            except Exception as e:
                return False, "[%s] 请求 /stream/process 失败: %r\n%s" % (case["name"], e, tail(log))
            if status != 200:
                return False, "[%s] HTTP %s（期望 200）: %s" % (case["name"], status, str(body)[:300])

            for f in ("size_mb", "chunk_kib", "min_amount"):
                if body.get(f) != spec[f]:
                    return False, "[%s] %s 回显不符: %r（期望 %r）" % (case["name"], f, body.get(f), spec[f])
            for f in ("bytes_read", "lines_read", "bytes_written", "lines_written",
                      "checksum", "output_checksum"):
                if body.get(f) != want[f]:
                    return False, "[%s] %s=%r 与 oracle 不一致（期望 %r）" % (
                        case["name"], f, body.get(f), want[f])

            # 真实落盘字节数必须与声称的字节数一致：只比对计数器会漏掉
            # "计数递增但内容被覆盖/没真正写出"这类静默错误（TS 侧就踩过一次）
            if body.get("output_file_bytes") != want["bytes_written"]:
                return False, ("[%s] output_file_bytes=%r 与声称的 bytes_written=%r 不符 "
                               "—— 内容并未真正按预期写出"
                               % (case["name"], body.get("output_file_bytes"), want["bytes_written"]))

            chunk_bytes = spec["chunk_kib"] * 1024
            want_chunks = -(-want["bytes_read"] // chunk_bytes)  # ceil
            if body.get("chunks") != want_chunks:
                return False, "[%s] chunks=%r（期望 %d = ceil(%d/%d)）" % (
                    case["name"], body.get("chunks"), want_chunks, want["bytes_read"], chunk_bytes)

            if body.get("cleanup") is not True:
                return False, "[%s] cleanup=%r —— 临时文件没有被删除（多跑几次会撑满磁盘）" % (
                    case["name"], body.get("cleanup"))

            for f in ("gen_ms", "proc_ms", "elapsed_ms", "throughput_mb_s"):
                v = body.get(f)
                if not isinstance(v, (int, float)) or v < 0:
                    return False, "[%s] %s 字段缺失或非法: %r" % (case["name"], f, v)

            # ⭐ 本场景的核心断言：内存增量必须与数据量无关
            cap = case.get("mem_cap_bytes")
            delta = body.get("rss_delta_bytes")
            if not isinstance(delta, (int, float)):
                return False, "[%s] rss_delta_bytes 字段缺失或非法: %r" % (case["name"], delta)
            if cap is not None and delta > cap:
                return False, ("[%s] rss_delta_bytes=%.1fMiB 超过上限 %.1fMiB —— "
                               "内存随数据量增长，实现并非流式（数据本身就有 %dMiB）"
                               % (case["name"], delta / 1048576.0, cap / 1048576.0, spec["size_mb"]))

            notes.append("%s %dms/%.1fMiB" % (case["name"], body.get("elapsed_ms"),
                                              delta / 1048576.0))

        return True, ("流式契约一致：%s（摘要与 oracle 逐字节相符，块数=ceil(bytes/chunk)，"
                      "临时文件已清理；RSS 增量随数据量保持恒定）" % " ｜ ".join(notes))
    finally:
        kill_tree(proc)
        subprocess.run(["pkill", "-9", "-f", os.path.join("scenarios", os.path.basename(os.path.dirname(d)))],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)


# ================================================================
# 场景 17：错误处理深水区（kind=error）
# ================================================================
# 四层 cause_chain：最外层 → 根因。五门语言必须用各自的链机制拼出**同一串字符串**。
ERR_CHAIN = ["handler: GET /errors/wrap_chain", "service: get profile",
             "repository: load user", "db: row 42 not found"]
ERR_DETAILS = ["email: required", "age: must be >= 0"]
# "未捕获异常是否自带调用栈"是语言层面的能力差异，不是实现缺陷 —— 逐语言声明预期：
#   Go：error 是值、panic 恢复后拿到的只是 any，不带栈（要栈得 debug.Stack() 现抓）
#   Rust：anyhow 只在 RUST_BACKTRACE=1 时抓 backtrace，默认关闭（零成本）
#   Java / Python / TS：异常对象天生带栈
ERR_STACK_EXPECT = {"java": True, "go": False, "python": True, "rust": False, "ts-node": True}
ERR_CASES = [
    {"kind": "not_found", "status": 404, "code": "NOT_FOUND", "message": "user 42 not found",
     "chain": ["user 42 not found"], "details": [], "recovered": False},
    {"kind": "validation", "status": 400, "code": "VALIDATION_FAILED", "message": "invalid request",
     "chain": ["invalid request"], "details": ERR_DETAILS, "recovered": False},
    {"kind": "wrap_chain", "status": 500, "code": "WRAPPED", "message": ERR_CHAIN[0],
     "chain": ERR_CHAIN, "details": [], "recovered": False},
    {"kind": "panic", "status": 500, "code": "INTERNAL", "message": "boom-17",
     "chain": ["boom-17"], "details": [], "recovered": True},
    {"kind": "async_detached", "status": 202, "code": "ACCEPTED", "message": "async work spawned",
     "chain": [], "details": [], "recovered": False},
]
# 脱离请求上下文的异步工作延迟 120ms 失败，给足观测窗口
ERR_ASYNC_TIMEOUT = 8.0


def verify_error(lang, port, d, log):
    """场景 17 契约级断言：错误形态的一致性与"错误有没有被观测到"。

    与前四个边界场景最大的不同：这里断言的是**可观测性**，而不只是返回值。
    - panic 用例之后服务必须还能应答（证明真的兜住了，而不是进程崩了）；
    - async_detached 之后 /stats.unhandled 必须 +1 —— 若某门语言静默丢弃了
      脱离上下文的错误，服务照样返回 200，只有这一个字段会暴露它。
    """
    free_port(port)
    with open(log, "a") as lf:
        proc = subprocess.Popen(start_cmd(lang, port, "error", d), cwd=d, env=ENV,
                                stdout=lf, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        if not poll_listen(port, RUN_POLL):
            return False, "no response on %d" % port + "\n" + tail(log)

        for i, case in enumerate(ERR_CASES, 1):
            tid = "v17-%s-%d" % (lang, i)
            try:
                status, body = http_json_get(port, "/errors/" + case["kind"],
                                             timeout=30, headers={"X-Trace-Id": tid})
            except Exception as e:
                return False, "[%s] 请求异常: %r\n%s" % (case["kind"], e, tail(log))
            if status != case["status"]:
                return False, "[%s] HTTP %s（期望 %d）: %s" % (
                    case["kind"], status, case["status"], str(body)[:300])
            if "_raw" in body:
                return False, "[%s] 响应不是 JSON: %s" % (case["kind"], body["_raw"])

            expects = [("kind", case["kind"]), ("code", case["code"]),
                       ("message", case["message"]), ("trace_id", tid),
                       ("cause_chain", case["chain"]), ("details", case["details"]),
                       ("recovered", case["recovered"])]
            if case["kind"] == "panic":
                expects.append(("stack_present", ERR_STACK_EXPECT[lang]))
            else:
                expects.append(("stack_present", False))
            for field, want in expects:
                got = body.get(field)
                if got != want:
                    return False, "[%s] 字段 %s = %r（期望 %r）" % (case["kind"], field, got, want)

        # 异步错误：轮询 /stats，等 detached 工作失败并被钩子记下来
        deadline = time.time() + ERR_ASYNC_TIMEOUT
        stats = {}
        while time.time() < deadline:
            try:
                _, stats = http_json_get(port, "/stats", timeout=10)
            except Exception as e:
                return False, ("panic 或异步错误之后服务已不可达 —— 未兜住的异步错误会打挂进程: %r\n%s"
                               % (e, tail(log)))
            if stats.get("unhandled", 0) >= 1:
                break
            time.sleep(0.25)

        if stats.get("unhandled", 0) < 1:
            return False, ("脱离请求上下文的错误没有被任何钩子捕获：/stats.unhandled=0 —— "
                           "HTTP 照样是 202，这就是本场景要暴露的静默失败")
        for field, want in (("last_unhandled", "async-boom-17"),
                            ("panics_recovered", 1),
                            ("handled", 4),
                            ("last_trace_id", "v17-%s-5" % lang)):
            got = stats.get(field)
            if got != want:
                return False, "/stats 字段 %s = %r（期望 %r）" % (field, got, want)

        return True, ("错误契约一致：五形态逐字段相符（含四层 cause_chain、details 与 trace_id 回显）；"
                      "未捕获异常已兜底且进程存活（panics_recovered=1）；"
                      "脱离上下文的异步错误被钩子捕获 last_unhandled=%s；stack_present=%s"
                      % (stats["last_unhandled"], ERR_STACK_EXPECT[lang]))
    finally:
        kill_tree(proc)
        subprocess.run(["pkill", "-9", "-f", os.path.join("scenarios", os.path.basename(os.path.dirname(d)))],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)


# ---------------- 契约级断言（http 类：通用用例引擎，自场景 00 起逐场景加强） ----------------
# 动机：此前的 http 场景只判定"端口通不通"——服务返回什么、返回得对不对一概不知。
# 这里提供声明式用例引擎：启动服务 → 逐个发请求 → 逐字段比对，
# 让每个 http 场景都能从"启动级"升级到"契约级"。
#
# json_match 匹配语义：
#  - dict：期望里的每个键都必须存在且递归匹配；exact=True 时键集合还必须完全相同
#  - list：等长 + 逐元素递归
#  - 标量：严格相等；bool 与 int 分开判（避免 True == 1 的假阳性）
def http_req(port, method, path, body=None, headers=None, timeout=30):
    """发一个 HTTP 请求，返回 (status, headers(键小写), body)。
    body 为 dict 时以 JSON 发送；为 str 时按原样发送（用于"畸形 JSON"用例）；
    响应按 Content-Type 决定是否解析为 JSON，失败退化为文本。
    用 http.client 而不是 urllib：前者默认不走代理，避免 HTTP_PROXY 把 localhost 请求劫持成 502。"""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        payload = None
        hdrs = dict(headers or {})
        if body is not None:
            payload = body if isinstance(body, str) else json.dumps(body)
            hdrs.setdefault("Content-Type", "application/json")
        conn.request(method, path, payload, hdrs)
        resp = conn.getresponse()
        raw = resp.read()
        text = raw.decode("utf-8", "replace")
        ctype = (resp.getheader("Content-Type") or "").lower()
        parsed = text
        if "json" in ctype:
            try:
                parsed = json.loads(text)
            except Exception:
                parsed = text
        return resp.status, {k.lower(): v for k, v in resp.getheaders()}, parsed
    finally:
        conn.close()


def json_match(expected, actual, exact=False, path="$"):
    """递归比对，返回错误信息列表（空列表 = 通过）。"""
    errs = []
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return ["%s: 期望对象，实际 %s" % (path, type(actual).__name__)]
        if exact and set(actual) != set(expected):
            errs.append("%s: 键集合不一致 actual=%s expected=%s"
                        % (path, sorted(actual), sorted(expected)))
        for k, v in expected.items():
            if k not in actual:
                errs.append("%s: 缺少键 %r" % (path, k))
            else:
                errs += json_match(v, actual[k], exact, "%s.%s" % (path, k))
    elif isinstance(expected, list):
        if not isinstance(actual, list):
            return ["%s: 期望数组，实际 %s" % (path, type(actual).__name__)]
        if len(expected) != len(actual):
            errs.append("%s: 数组长度 %d != %d" % (path, len(actual), len(expected)))
        else:
            for i, (e, a) in enumerate(zip(expected, actual)):
                errs += json_match(e, a, exact, "%s[%d]" % (path, i))
    elif isinstance(expected, bool) or isinstance(actual, bool):
        if type(expected) is not type(actual) or expected != actual:
            errs.append("%s: %r != %r" % (path, actual, expected))
    elif expected != actual:
        errs.append("%s: %r != %r" % (path, actual, expected))
    return errs


def verify_cases(lang, port, d, log, cases, env=None):
    """契约级断言引擎。
    用例字段：name / method / path / body / headers / status / status_in /
             content_type / json(+exact) / assert(自定义校验)。
    assert 签名：f(status, headers, body, fails, label)——往里 append 错误信息即可。"""
    free_port(port)
    with open(log, "a") as lf:
        proc = subprocess.Popen(start_cmd(lang, port, "http", d), cwd=d, env=env or ENV,
                                stdout=lf, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        if not poll_listen(port, RUN_POLL):
            return False, "no response on %d" % port + "\n" + tail(log)
        fails = []
        for c in cases:
            label = c.get("name", "%s %s" % (c.get("method", "GET"), c.get("path", "/")))
            try:
                status, headers, body = http_req(port, c.get("method", "GET"), c.get("path", "/"),
                                                 c.get("body"), c.get("headers"))
            except Exception as e:
                fails.append("[%s] 请求失败: %r" % (label, e))
                continue
            if "status" in c and status != c["status"]:
                fails.append("[%s] HTTP %d（期望 %d）" % (label, status, c["status"]))
            if "status_in" in c and status not in c["status_in"]:
                fails.append("[%s] HTTP %d（期望 %s 之一）" % (label, status, c["status_in"]))
            if "content_type" in c and c["content_type"] not in headers.get("content-type", ""):
                fails.append("[%s] Content-Type=%r 不含 %r"
                             % (label, headers.get("content-type", ""), c["content_type"]))
            if "json" in c:
                fails += ["[%s] %s" % (label, e)
                          for e in json_match(c["json"], body, exact=c.get("exact", False))]
            if "assert" in c:
                c["assert"](status, headers, body, fails, label)
        if fails:
            return False, "；".join(fails[:5]) + ("……共 %d 处不符" % len(fails) if len(fails) > 5 else "")
        return True, "%d 个用例逐字段通过" % len(cases)
    finally:
        kill_tree(proc)
        subprocess.run(["pkill", "-9", "-f", os.path.join("scenarios", os.path.basename(os.path.dirname(d)))],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)


# ================= 场景 00：最小 HTTP 服务 =================
# 契约（README 已记载的行为 + 显式化的边界行为）：
#   GET /hello?name=X → 200 {"msg":"hello X"}；X 缺省或为空串 → "hello world"
#   未匹配路径        → 404（响应体因框架而异，只断言状态码）
#   非 GET 方法       → 405（fastify 默认给 404，实现侧已抹平）
CASES_00 = [
    {"name": "缺省 name", "method": "GET", "path": "/hello", "status": 200,
     "content_type": "application/json", "json": {"msg": "hello world"}, "exact": True},
    {"name": "显式 name", "method": "GET", "path": "/hello?name=Trae", "status": 200,
     "json": {"msg": "hello Trae"}, "exact": True},
    {"name": "空 name 按缺省处理", "method": "GET", "path": "/hello?name=", "status": 200,
     "json": {"msg": "hello world"}, "exact": True},
    {"name": "unicode name 原样拼接", "method": "GET", "path": "/hello?name=%E4%B8%96%E7%95%8C",
     "status": 200, "json": {"msg": "hello 世界"}, "exact": True},
    {"name": "未匹配路径", "method": "GET", "path": "/nope", "status": 404},
    {"name": "方法不允许", "method": "POST", "path": "/hello", "status": 405},
]


def verify_00(lang, port, d, log):
    return verify_cases(lang, port, d, log, CASES_00)


# ================= 场景 01：JSON 序列化/反序列化 =================
# 契约载荷：**键名按字母序排列**。Go 的 map 与 Rust 的 BTreeMap 按 key 排序输出，
# Python/Java/TS 保留输入顺序——用排序输入作载荷，五门语言的 `json` 字符串才能逐字节比对。
P01_PAYLOAD = {"age": 28, "cn": "世界", "empty": [], "html": "<b> & 'x'",
               "nested": {"a": 2, "z": 1}, "nil": None, "tags": ["a", "b"]}
# 契约规定的规范序列化形式：紧凑分隔符、非 ASCII 不转义、HTML 字符不转义。
# （Go 的 json.Marshal 默认把 < > & 转义成 \u003c 等，Python 的 json.dumps 默认把非 ASCII
#   转义成 \uXXXX——都不符合"标准 JSON"，实现侧已按本契约修正。）
P01_CANON = json.dumps(P01_PAYLOAD, ensure_ascii=False, separators=(",", ":"))
P01_BYTES = len(P01_CANON.encode("utf-8"))
# /demo 与 /bench 共用的标准对象（五门语言字段顺序一致：id,name,email,age,tags,address,scores）
P01_DEMO = {"id": 1, "name": "Alice", "email": None, "age": 28,
            "tags": ["engineer", "java"],
            "address": {"city": "Beijing", "zip": "100000"},
            "scores": []}
P01_DEMO_BYTES = len(json.dumps(P01_DEMO, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _p01_check_serialize(status, headers, body, fails, label):
    if not isinstance(body, dict):
        fails.append("[%s] 响应不是 JSON 对象: %r" % (label, body))
        return
    if body.get("json") != P01_CANON:
        fails.append("[%s] json 字段非规范形式: %r" % (label, body.get("json")))
    if body.get("bytes") != P01_BYTES:
        fails.append("[%s] bytes=%r（期望 UTF-8 字节数 %d）" % (label, body.get("bytes"), P01_BYTES))
    if not isinstance(body.get("time_us"), int) or isinstance(body.get("time_us"), bool) \
            or body.get("time_us") < 0:
        fails.append("[%s] time_us=%r 不是非负整数" % (label, body.get("time_us")))
    try:
        if json.loads(body.get("pretty") or "") != P01_PAYLOAD:
            fails.append("[%s] pretty 解析回的对象与载荷不一致" % label)
    except Exception as e:
        fails.append("[%s] pretty 无法解析: %r" % (label, e))


def _p01_check_deserialize(status, headers, body, fails, label):
    if not isinstance(body, dict):
        fails.append("[%s] 响应不是 JSON 对象: %r" % (label, body))
        return
    fails += json_match(P01_PAYLOAD, body.get("parsed"), exact=True, path="%s.parsed" % label)
    if body.get("size") != P01_BYTES:
        fails.append("[%s] size=%r（期望 UTF-8 字节数 %d，不是字符数）"
                     % (label, body.get("size"), P01_BYTES))


def _p01_check_roundtrip(status, headers, body, fails, label):
    if not isinstance(body, dict):
        fails.append("[%s] 响应不是 JSON 对象: %r" % (label, body))
        return
    if body.get("equal") is not True:
        fails.append("[%s] equal=%r（期望 true）" % (label, body.get("equal")))
    for f in ("original_json", "roundtrip_json"):
        if body.get(f) != P01_CANON:
            fails.append("[%s] %s=%r 与规范形式不一致" % (label, f, body.get(f)))
    for f in ("original_bytes", "roundtrip_bytes"):
        if body.get(f) != P01_BYTES:
            fails.append("[%s] %s=%r（期望 %d）" % (label, f, body.get(f), P01_BYTES))


def _p01_check_bench(status, headers, body, fails, label):
    if not isinstance(body, dict):
        fails.append("[%s] 响应不是 JSON 对象: %r" % (label, body))
        return
    if body.get("iterations") != 10000:
        fails.append("[%s] iterations=%r（期望 10000）" % (label, body.get("iterations")))
    if body.get("json_size_bytes") != P01_DEMO_BYTES:
        fails.append("[%s] json_size_bytes=%r（期望 demo 对象序列化字节数 %d）"
                     % (label, body.get("json_size_bytes"), P01_DEMO_BYTES))
    if not isinstance(body.get("language"), str) or not body.get("language"):
        fails.append("[%s] language=%r 不是非空字符串" % (label, body.get("language")))
    for f in ("total_time_ms", "avg_time_us"):
        v = body.get(f)
        if not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0:
            fails.append("[%s] %s=%r 不是非负数值" % (label, f, v))


CASES_01 = [
    {"name": "GET /demo 标准测试对象", "method": "GET", "path": "/demo", "status": 200,
     "json": P01_DEMO, "exact": True},
    {"name": "POST /serialize 规范序列化", "method": "POST", "path": "/serialize",
     "body": P01_PAYLOAD, "status": 200, "assert": _p01_check_serialize},
    {"name": "POST /deserialize 回解析", "method": "POST", "path": "/deserialize",
     "body": {"json_string": P01_CANON}, "status": 200, "assert": _p01_check_deserialize},
    {"name": "POST /roundtrip 往返保真", "method": "POST", "path": "/roundtrip",
     "body": P01_PAYLOAD, "status": 200, "assert": _p01_check_roundtrip},
    {"name": "GET /bench 性能基准字段", "method": "GET", "path": "/bench", "status": 200,
     "assert": _p01_check_bench},
]


def verify_01(lang, port, d, log):
    return verify_cases(lang, port, d, log, CASES_01)


# ================= 场景 02：并发任务处理 =================
# 统一契约（README「统一接口」小节的显式化 + 抹平后的边界行为）：
#   POST /run，字段 task_count / task_delay_ms / concurrency，缺省 → 100/100/10
#   响应键集合恰好 {total_tasks, concurrency, total_time_ms, throughput, task_delay_ms, results}
#   results[i] = {id, status, duration_ms}，id 按 0..n-1 严格保序，status 全 "ok"
#   duration_ms ∈ [delay-2, delay+1000]（sleep 至少约 delay 毫秒；下界留 2ms 容忍
#       asyncio 经 kqueue 的毫秒取整误差，其余四门用精确保眠会超过 delay）
#   concurrency 回显 min(请求 concurrency, task_count)
#   throughput ≈ task_count / (total_time_ms/1000)（两位小数，容差 0.02）
#   total_time_ms ∈ [ceil(n/c)*delay*0.9, ceil(n/c)*delay*1.5+300]
#       —— 下界证明"限流真的生效"（不限流会低到 ~delay），上界证明"没有退化成串行"（串行是 n*delay）
#   非法入参（task_count<1 / concurrency<1 / task_delay_ms<0 / 非整数 / 畸形 JSON / 空 body）→ 400
#   非 POST 方法 → 405（fastify 默认给 404，实现侧已抹平）
P02_STD = (10, 50, 5)     # (task_count, task_delay_ms, concurrency)
P02_WIDE = (4, 40, 10)    # concurrency > task_count → 回显 min(c, n)
P02_ZERO = (8, 0, 4)      # delay=0 的边界
P02_DUAL = (6, 60, 3)     # 并发双请求用例


def _p02_check_run(n, delay, conc):
    """标准 /run 响应的契约校验器（n=任务数, delay=每任务毫秒, conc=请求并发度）。"""
    eff_conc = min(conc, n)
    waves = math.ceil(n / eff_conc) if eff_conc > 0 else 1
    ideal = waves * delay
    lo, hi = ideal * 0.9, ideal * 1.5 + 300

    def assert_fn(status, headers, body, fails, label):
        if not isinstance(body, dict):
            fails.append("[%s] 响应不是 JSON 对象: %r" % (label, body))
            return
        want_keys = {"total_tasks", "concurrency", "total_time_ms", "throughput",
                     "task_delay_ms", "results"}
        if set(body) != want_keys:
            fails.append("[%s] 键集合不一致: %s" % (label, sorted(body)))
            return
        if body["total_tasks"] != n:
            fails.append("[%s] total_tasks=%r（期望 %d）" % (label, body["total_tasks"], n))
        if body["task_delay_ms"] != delay:
            fails.append("[%s] task_delay_ms=%r（期望 %d）" % (label, body["task_delay_ms"], delay))
        if body["concurrency"] != eff_conc:
            fails.append("[%s] concurrency=%r（期望 min(c,n)=%d）"
                         % (label, body["concurrency"], eff_conc))
        total = body["total_time_ms"]
        if not isinstance(total, int) or isinstance(total, bool) or total < 0:
            fails.append("[%s] total_time_ms=%r 不是非负整数" % (label, total))
            return
        if total < lo:
            fails.append("[%s] total_time_ms=%d < 下界 %.0f —— 并发限流疑似未生效"
                         % (label, total, lo))
        if total > hi:
            fails.append("[%s] total_time_ms=%d > 上界 %.0f —— 疑似退化成串行（串行应为 %d）"
                         % (label, total, hi, n * delay))
        tp = body["throughput"]
        if not isinstance(tp, (int, float)) or isinstance(tp, bool):
            fails.append("[%s] throughput=%r 不是数值" % (label, tp))
        else:
            want_tp = round(n * 1000.0 / total, 2) if total > 0 else float(n)
            if abs(tp - want_tp) > 0.02:
                fails.append("[%s] throughput=%r 与自洽值 %.2f 不符（容差 0.02）"
                             % (label, tp, want_tp))
        results = body["results"]
        if not isinstance(results, list) or len(results) != n:
            fails.append("[%s] results 长度 %r（期望 %d）"
                         % (label, len(results) if isinstance(results, list) else results, n))
            return
        ids = [r.get("id") if isinstance(r, dict) else None for r in results]
        if ids != list(range(n)):
            fails.append("[%s] results 的 id 序列不是严格 0..%d（保序契约）" % (label, n - 1))
        for i, r in enumerate(results):
            if not isinstance(r, dict) or set(r) != {"id", "status", "duration_ms"}:
                fails.append("[%s] results[%d] 键集合异常: %r" % (label, i, r))
                continue
            if r["status"] != "ok":
                fails.append("[%s] results[%d].status=%r（期望 ok）" % (label, i, r["status"]))
            dms = r["duration_ms"]
            if not isinstance(dms, int) or isinstance(dms, bool):
                fails.append("[%s] results[%d].duration_ms=%r 不是整数" % (label, i, dms))
                continue
            if dms < delay - 2:
                # 下界留 2ms 容忍：Python 的 asyncio.sleep 经 kqueue 毫秒取整，
                # 实测 sleep(100ms) 可能只测到 99ms（其余四门用精确保眠会超过 delay）
                fails.append("[%s] results[%d].duration_ms=%d 明显小于 delay=%d —— sleep 没睡够？"
                             % (label, i, dms, delay))
            if dms > delay + 1000:
                fails.append("[%s] results[%d].duration_ms=%d 远超 delay=%d —— 单位可能错了"
                             % (label, i, dms, delay))
            if dms > total + 5:
                fails.append("[%s] results[%d].duration_ms=%d > total_time_ms=%d —— 单项超过总时长"
                             % (label, i, dms, total))

    return assert_fn


def _p02_dual_assert(port, n, delay, conc):
    """并发双请求：两个 /run 同时在途，验证共享状态（结果切片/线程池/信号量）无污染。"""
    body = {"task_count": n, "task_delay_ms": delay, "concurrency": conc}
    check = _p02_check_run(n, delay, conc)

    def assert_fn(status, headers, resp_body, fails, label):
        outcomes = [None, None]

        def worker(i):
            try:
                outcomes[i] = http_req(port, "POST", "/run", body)
            except Exception as e:
                # 用 dict 包装而不是 tuple：http_req 的正常返回值也是 tuple，
                # 曾经用 ("exc", repr(e)) 作标记，把每次成功响应都误判成"请求异常"
                outcomes[i] = {"exc": repr(e)}

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        for i, o in enumerate(outcomes):
            if isinstance(o, dict) and "exc" in o:
                fails.append("[%s#%d] 请求异常: %s" % (label, i, o["exc"]))
                continue
            check(o[0], o[1], o[2], fails, "%s#%d" % (label, i))
        # 主线程这一发同样按契约校验（三次采样互相独立）
        check(status, headers, resp_body, fails, label)

    return assert_fn


CASES_02 = [
    {"name": "标准并发（10 任务/5 并发/50ms）", "method": "POST", "path": "/run",
     "body": {"task_count": P02_STD[0], "task_delay_ms": P02_STD[1], "concurrency": P02_STD[2]},
     "status": 200, "assert": _p02_check_run(*P02_STD)},
    {"name": "并发数大于任务数（min 语义）", "method": "POST", "path": "/run",
     "body": {"task_count": P02_WIDE[0], "task_delay_ms": P02_WIDE[1], "concurrency": P02_WIDE[2]},
     "status": 200, "assert": _p02_check_run(*P02_WIDE)},
    {"name": "零延迟任务", "method": "POST", "path": "/run",
     "body": {"task_count": P02_ZERO[0], "task_delay_ms": P02_ZERO[1], "concurrency": P02_ZERO[2]},
     "status": 200, "assert": _p02_check_run(*P02_ZERO)},
    {"name": "字段缺省走默认值 100/100/10", "method": "POST", "path": "/run", "body": {},
     "status": 200, "assert": _p02_check_run(100, 100, 10)},
    {"name": "非法值 task_count=0 → 400", "method": "POST", "path": "/run",
     "body": {"task_count": 0, "task_delay_ms": 10, "concurrency": 2}, "status": 400},
    {"name": "非法值 concurrency=0 → 400", "method": "POST", "path": "/run",
     "body": {"task_count": 4, "task_delay_ms": 10, "concurrency": 0}, "status": 400},
    {"name": "非法值 task_delay_ms=-1 → 400", "method": "POST", "path": "/run",
     "body": {"task_count": 4, "task_delay_ms": -1, "concurrency": 2}, "status": 400},
    {"name": "非整数 task_count → 400", "method": "POST", "path": "/run",
     "body": {"task_count": "abc", "task_delay_ms": 10, "concurrency": 2}, "status": 400},
    {"name": "畸形 JSON body → 400", "method": "POST", "path": "/run",
     "body": "{not-json", "status": 400},
    {"name": "空 body → 400", "method": "POST", "path": "/run", "body": None, "status": 400},
    {"name": "方法不允许 GET /run → 405", "method": "GET", "path": "/run", "status": 405},
]


def verify_02(lang, port, d, log):
    cases = list(CASES_02)
    cases.append({"name": "并发双请求无串扰", "method": "POST", "path": "/run",
                  "body": {"task_count": P02_DUAL[0], "task_delay_ms": P02_DUAL[1],
                           "concurrency": P02_DUAL[2]},
                  "status": 200, "assert": _p02_dual_assert(port, *P02_DUAL)})
    return verify_cases(lang, port, d, log, cases)


# ================= 场景 04：文件读写 & 目录遍历 =================
# 统一契约（README「统一 API 契约」的显式化 + 抹平后的边界行为）：
#   POST /file/write {path, content, append?} → 200
#       {"success":true,"path":<回显>,"bytes_written":<UTF-8 字节数>,"append":<回显>}
#       content 为字符串 → 原样写入；为其他类型 → 规范 JSON
#       （紧凑分隔符、非 ASCII 不转义、HTML 字符不转义；五门语言逐字节一致）
#       写失败 → 200 + {"success":false,"error":...}（不回 5xx）
#   GET /file/read?path= → {"path","content","bytes"}；文件不存在 404，是目录 400，
#       path 缺失/空串 400
#   GET /file/scan?dir=&recursive= → {"dir","recursive","files","total_bytes"}；
#       recursive 缺省 true、仅字面 "false" 为 false；目录不存在 404，是文件 400，
#       dir 缺失/空串 400；只统计常规文件
#   方法不匹配 → 405（fastify 默认给 404，实现侧已抹平）；未匹配路径 → 404
#   除状态码/字段外，"声称的字节数"必须与本地独立读磁盘的结果一致（声称值与真实值分开验）
P04_STR = "世界 <b> & 'x'\n第二行"                     # 含非 ASCII / HTML 字符 / 换行
P04_OBJ = {"cn": "世界", "html": "<b> & 'x'", "n": 42}  # 键按字母序 → 五门语言序列化逐字节一致
P04_OBJ_CANON = json.dumps(P04_OBJ, ensure_ascii=False, separators=(",", ":"))
P04_A, P04_C, P04_B = "aaaaaaaaaa", "字节字节", "bbbbb"  # scan 夹具：顶层两个 + 子目录一个


def _p04_local_bytes(path):
    """本地独立 oracle：直接读磁盘，与接口"声称的字节数"分开验。"""
    with open(path, "rb") as fh:
        return fh.read()


def _p04_write_assert(path, content_str, append=False, full_content=None):
    """写接口断言：响应四个字段 + 声称字节数与磁盘真实内容双验。"""
    want_bytes = len(content_str.encode("utf-8"))
    disk_want = (full_content if full_content is not None else content_str).encode("utf-8")

    def assert_fn(status, headers, body, fails, label):
        if not isinstance(body, dict):
            fails.append("[%s] 响应不是 JSON 对象: %r" % (label, body))
            return
        if set(body) != {"success", "path", "bytes_written", "append"}:
            fails.append("[%s] 键集合不一致: %s" % (label, sorted(body)))
        if body.get("success") is not True:
            fails.append("[%s] success=%r（期望 true）" % (label, body.get("success")))
        if body.get("append") is not append:
            fails.append("[%s] append=%r（期望 %r）" % (label, body.get("append"), append))
        if body.get("path") != path:
            fails.append("[%s] path 回显不一致: %r" % (label, body.get("path")))
        if body.get("bytes_written") != want_bytes:
            fails.append("[%s] bytes_written=%r（期望本次写入 %d 字节）"
                         % (label, body.get("bytes_written"), want_bytes))
        try:
            actual = _p04_local_bytes(path)
        except Exception as e:
            fails.append("[%s] 本地读不到刚写的文件 %s: %r" % (label, path, e))
            return
        if len(actual) != len(disk_want):
            fails.append("[%s] 磁盘文件大小 %d 与期望 %d 不一致（声称值与真实值分裂）"
                         % (label, len(actual), len(disk_want)))
        if actual != disk_want:
            fails.append("[%s] 磁盘文件内容与期望不一致（序列化形式漂移？）" % label)

    return assert_fn


def _p04_read_assert(path, content_str):
    """读接口断言：content 原样回显 + bytes 为 UTF-8 字节数。"""
    want_bytes = len(content_str.encode("utf-8"))

    def assert_fn(status, headers, body, fails, label):
        if not isinstance(body, dict):
            fails.append("[%s] 响应不是 JSON 对象: %r" % (label, body))
            return
        if set(body) != {"path", "content", "bytes"}:
            fails.append("[%s] 键集合不一致: %s" % (label, sorted(body)))
        if body.get("path") != path:
            fails.append("[%s] path 回显不一致: %r" % (label, body.get("path")))
        if body.get("content") != content_str:
            fails.append("[%s] content 与写入内容不一致: %r" % (label, body.get("content")))
        if body.get("bytes") != want_bytes:
            fails.append("[%s] bytes=%r（期望 UTF-8 字节数 %d，不是字符数）"
                         % (label, body.get("bytes"), want_bytes))

    return assert_fn


def _p04_scan_assert(dir_path, recursive):
    """扫描断言：files/total_bytes 与本地独立遍历磁盘的 oracle 比对。"""

    def assert_fn(status, headers, body, fails, label):
        if not isinstance(body, dict):
            fails.append("[%s] 响应不是 JSON 对象: %r" % (label, body))
            return
        if set(body) != {"dir", "recursive", "files", "total_bytes"}:
            fails.append("[%s] 键集合不一致: %s" % (label, sorted(body)))
        if body.get("dir") != dir_path:
            fails.append("[%s] dir 回显不一致: %r" % (label, body.get("dir")))
        if body.get("recursive") is not recursive:
            fails.append("[%s] recursive=%r（期望 %r）" % (label, body.get("recursive"), recursive))
        want_files, want_bytes = 0, 0
        if recursive:
            for root, _dirs, files in os.walk(dir_path):
                for fn in files:
                    fp = os.path.join(root, fn)
                    if os.path.isfile(fp):
                        want_files += 1
                        want_bytes += os.path.getsize(fp)
        else:
            try:
                entries = os.listdir(dir_path)
            except OSError as e:
                fails.append("[%s] oracle 无法列举目录 %s: %r（前置写夹具应已创建它）"
                             % (label, dir_path, e))
                return
            for fn in entries:
                fp = os.path.join(dir_path, fn)
                if os.path.isfile(fp):
                    want_files += 1
                    want_bytes += os.path.getsize(fp)
        if body.get("files") != want_files:
            fails.append("[%s] files=%r（oracle %d）" % (label, body.get("files"), want_files))
        if body.get("total_bytes") != want_bytes:
            fails.append("[%s] total_bytes=%r（oracle %d）"
                         % (label, body.get("total_bytes"), want_bytes))

    return assert_fn


def _p04_write_fail_assert():
    def assert_fn(status, headers, body, fails, label):
        if status != 200:
            fails.append("[%s] HTTP %d（期望 200：写失败用 success:false 表达，不回 5xx）"
                         % (label, status))
        if not isinstance(body, dict):
            fails.append("[%s] 响应不是 JSON 对象: %r" % (label, body))
        elif body.get("success") is not False:
            fails.append("[%s] success=%r（期望 false）" % (label, body.get("success")))
        elif "error" not in body:
            fails.append("[%s] 缺少 error 详情字段" % label)

    return assert_fn


def _p04_deep_assert(path):
    def assert_fn(status, headers, body, fails, label):
        if not isinstance(body, dict) or body.get("success") is not True:
            fails.append("[%s] success=%r（期望 true）"
                         % (label, body.get("success") if isinstance(body, dict) else body))
        if not os.path.exists(path):
            fails.append("[%s] 深层目录/文件未被创建: %s" % (label, path))

    return assert_fn


def _p04_cases(tmp):
    """按临时夹具目录生成用例列表（路径带查询参数时做 URL 编码）。"""
    from urllib.parse import quote
    q = quote
    f_str, f_obj = os.path.join(tmp, "s.txt"), os.path.join(tmp, "o.json")
    f_app, f_deep = os.path.join(tmp, "app.txt"), os.path.join(tmp, "deep", "a", "b", "c.txt")
    scan_dir = os.path.join(tmp, "scan")
    f_a, f_c, f_b = (os.path.join(scan_dir, "a.txt"), os.path.join(scan_dir, "c.bin"),
                     os.path.join(scan_dir, "sub", "b.txt"))
    f_empty = os.path.join(tmp, "empty")
    f_block, f_block_child = os.path.join(tmp, "blocker"), os.path.join(tmp, "blocker", "child.json")
    os.makedirs(f_empty, exist_ok=True)  # 空目录夹具（验证器侧创建，不走接口）

    return [
        # ---- 写 + 本地磁盘双验 ----
        {"name": "写字符串内容（含非 ASCII/HTML/换行）", "method": "POST", "path": "/file/write",
         "body": {"path": f_str, "content": P04_STR, "append": False}, "status": 200,
         "assert": _p04_write_assert(f_str, P04_STR)},
        {"name": "读回字符串内容", "method": "GET", "path": "/file/read?path=" + q(f_str),
         "status": 200, "assert": _p04_read_assert(f_str, P04_STR)},
        {"name": "写对象内容（规范 JSON）", "method": "POST", "path": "/file/write",
         "body": {"path": f_obj, "content": P04_OBJ, "append": False}, "status": 200,
         "assert": _p04_write_assert(f_obj, P04_OBJ_CANON)},
        {"name": "读回对象内容", "method": "GET", "path": "/file/read?path=" + q(f_obj),
         "status": 200, "assert": _p04_read_assert(f_obj, P04_OBJ_CANON)},
        # ---- 覆盖 + 追加 ----
        {"name": "覆盖写 AB", "method": "POST", "path": "/file/write",
         "body": {"path": f_app, "content": "AB", "append": False}, "status": 200,
         "assert": _p04_write_assert(f_app, "AB")},
        {"name": "追加 CD", "method": "POST", "path": "/file/write",
         "body": {"path": f_app, "content": "CD", "append": True}, "status": 200,
         "assert": _p04_write_assert(f_app, "CD", append=True, full_content="ABCD")},
        {"name": "读回合并内容 ABCD", "method": "GET", "path": "/file/read?path=" + q(f_app),
         "status": 200, "assert": _p04_read_assert(f_app, "ABCD")},
        # ---- 深层目录自动创建 ----
        {"name": "深层目录自动创建", "method": "POST", "path": "/file/write",
         "body": {"path": f_deep, "content": "deep", "append": False}, "status": 200,
         "assert": _p04_deep_assert(f_deep)},
        # ---- scan 夹具（经接口写入，父目录由服务端创建）----
        {"name": "夹具写入 a.txt", "method": "POST", "path": "/file/write",
         "body": {"path": f_a, "content": P04_A}, "status": 200,
         "assert": _p04_write_assert(f_a, P04_A)},
        {"name": "夹具写入 c.bin", "method": "POST", "path": "/file/write",
         "body": {"path": f_c, "content": P04_C}, "status": 200,
         "assert": _p04_write_assert(f_c, P04_C)},
        {"name": "夹具写入 sub/b.txt", "method": "POST", "path": "/file/write",
         "body": {"path": f_b, "content": P04_B}, "status": 200,
         "assert": _p04_write_assert(f_b, P04_B)},
        # ---- 目录遍历（oracle = 本地独立遍历）----
        {"name": "递归扫描（3 文件/2 层）", "method": "GET",
         "path": "/file/scan?dir=" + q(scan_dir), "status": 200,
         "assert": _p04_scan_assert(scan_dir, True)},
        {"name": "非递归扫描（只数一层）", "method": "GET",
         "path": "/file/scan?dir=" + q(scan_dir) + "&recursive=false", "status": 200,
         "assert": _p04_scan_assert(scan_dir, False)},
        {"name": "空目录扫描", "method": "GET", "path": "/file/scan?dir=" + q(f_empty),
         "status": 200, "assert": _p04_scan_assert(f_empty, True)},
        # ---- 错误分支 ----
        {"name": "读不存在文件 → 404", "method": "GET",
         "path": "/file/read?path=" + q(os.path.join(tmp, "nope.txt")), "status": 404},
        {"name": "读目录 → 400", "method": "GET", "path": "/file/read?path=" + q(scan_dir),
         "status": 400},
        {"name": "扫描不存在目录 → 404", "method": "GET",
         "path": "/file/scan?dir=" + q(os.path.join(tmp, "no-dir")), "status": 404},
        {"name": "扫描一个文件 → 400", "method": "GET", "path": "/file/scan?dir=" + q(f_str),
         "status": 400},
        {"name": "写失败：父路径是文件", "method": "POST", "path": "/file/write",
         "body": {"path": f_block, "content": "x"}, "status": 200,
         "assert": _p04_write_assert(f_block, "x")},
        {"name": "写失败 → 200 + success:false", "method": "POST", "path": "/file/write",
         "body": {"path": f_block_child, "content": "y"}, "status": 200,
         "assert": _p04_write_fail_assert()},
        # ---- 参数与方法边界 ----
        {"name": "read 缺失 path 参数 → 400", "method": "GET", "path": "/file/read", "status": 400},
        {"name": "read 空 path 参数 → 400", "method": "GET", "path": "/file/read?path=", "status": 400},
        {"name": "scan 缺失 dir 参数 → 400", "method": "GET", "path": "/file/scan", "status": 400},
        {"name": "scan 空 dir 参数 → 400", "method": "GET", "path": "/file/scan?dir=", "status": 400},
        {"name": "POST /file/read → 405", "method": "POST", "path": "/file/read", "status": 405},
        {"name": "GET /file/write → 405", "method": "GET", "path": "/file/write", "status": 405},
        {"name": "POST /file/scan → 405", "method": "POST", "path": "/file/scan", "status": 405},
        {"name": "未匹配路径 → 404", "method": "GET", "path": "/file/nope", "status": 404},
    ]


def verify_04(lang, port, d, log):
    tmp = tempfile.mkdtemp(prefix="wb-verify-04-")
    try:
        return verify_cases(lang, port, d, log, _p04_cases(tmp))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# kind == "contract" 的场景注册表。SCENARIOS 定义在文件顶部，这里用名字查表
# （而不是在 SCENARIOS 里直接引用函数）以避免前向引用。
CONTRACT_VERIFIERS = {
    "00-hello-http": verify_00,
    "01-json-serialize": verify_01,
    "02-concurrent-task": verify_02,
    "04-file-io": verify_04,
}


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
                    elif kind == "stream":
                        ok, note = verify_stream(lang, sc["ports"][lang], d, log)
                    elif kind == "error":
                        ok, note = verify_error(lang, sc["ports"][lang], d, log)
                    elif kind == "contract":
                        # 契约级：逐用例发请求 + 逐字段比对（见 CONTRACT_VERIFIERS）
                        ok, note = CONTRACT_VERIFIERS[name](lang, sc["ports"][lang], d, log)
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
