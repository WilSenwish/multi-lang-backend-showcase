#!/usr/bin/env python3
"""场景 12 定点复核：验证"收到 SIGTERM 后真的会优雅退出，并且**等完在途请求**"。

判定依据（三条全过才算 PASS）：
  1. 监听端口被释放（监听进程自己退出了；不看 tsx watch / mvn 这类包装进程）
  2. 在途的 /api/long-task 请求**正常拿到响应**（没有被关闭流程切断）
  3. 日志出现关闭完成标记，且无崩溃特征

用法:
  python3 .wb_verify/check_graceful.py                 # 跑全部 5 种语言
  python3 .wb_verify/check_graceful.py python          # 只跑某语言
  python3 .wb_verify/check_graceful.py python "cmd"    # 覆盖启动命令
"""
from __future__ import annotations

import http.client
import os
import signal
import socket
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CMDS = {
    "java": (["mvn", "-q", "-DskipTests", "spring-boot:run"], 8130),
    "go": (["go", "run", "."], 8131),
    "python": (["bash", "-c", "uvicorn main:app --port 8132"], 8132),
    "rust": (["cargo", "run"], 8133),
    "ts-node": (["npm", "run", "dev"], 8134),
}
OK_MARKERS = ("shutdown complete",)
BAD_MARKERS = ("traceback", "attributeerror", "panic", "error[e",
               "exception in callback", "address already in use")
LONG_TASK_PATH = "/api/long-task"


def wait_listen(port: int, timeout: float) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=2):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def wait_release(port: int, timeout: float) -> float:
    t0 = time.time()
    end = t0 + timeout
    while time.time() < end:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=2):
                time.sleep(0.3)
        except OSError:
            return time.time() - t0
    return -1.0


def listener_pid(port: int) -> int | None:
    """取"在监听该端口"的进程 PID。

    必须加 -sTCP:LISTEN：否则 lsof -ti :PORT 会把**连到该端口的客户端**也列出来
    （验证脚本自己就在发请求），一旦取到自己的 pid 再 kill，就变成自己杀自己。
    """
    out = subprocess.run(["lsof", "-nP", "-iTCP:%d" % port, "-sTCP:LISTEN", "-t"],
                         capture_output=True, text=True).stdout
    me = os.getpid()
    for p in out.split():
        if p.isdigit() and int(p) != me:
            return int(p)
    return None


def free_port(port: int) -> None:
    """启动前先清掉占用端口的残留实例 —— 否则新实例绑不上端口，
    请求会被旧实例接走，测量结果全错（表现为日志里的 'address already in use'）。"""
    out = subprocess.run(["lsof", "-nP", "-iTCP:%d" % port, "-sTCP:LISTEN", "-t"],
                         capture_output=True, text=True).stdout
    me = os.getpid()
    for p in out.split():
        if p.isdigit() and int(p) != me:
            try:
                os.kill(int(p), signal.SIGKILL)
                print("  (清理端口 %d 上的残留进程 %s)" % (port, p))
            except Exception as e:
                print("  (清理端口 %d 的进程 %s 失败: %s)" % (port, p, e))
    time.sleep(1)


def fire_long_task(port: int, result: dict) -> None:
    t0 = time.time()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
        conn.request("GET", LONG_TASK_PATH)
        resp = conn.getresponse()
        body = resp.read().decode("utf-8", "replace")
        result.update(ok=True, status=resp.status, body=body[:200], elapsed=time.time() - t0)
    except Exception as e:
        result.update(ok=False, error=repr(e), elapsed=time.time() - t0)


def check_lang(lang: str, override_cmd: str | None = None) -> bool:
    cmd, port = CMDS[lang]
    if override_cmd:
        cmd = ["bash", "-c", override_cmd]
    d = os.path.join(ROOT, "scenarios/12-graceful-shutdown", lang)
    log = "/tmp/graceful_%s.log" % lang.replace("-", "_")
    open(log, "w").close()

    env = dict(os.environ)
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
              "SERVER__PORT", "SERVER_PORT", "PORT"):
        env.pop(k, None)
    env["PYTHONUNBUFFERED"] = "1"
    env["JAVA_HOME"] = "/opt/homebrew/opt/openjdk@17"
    env["PATH"] = (env["JAVA_HOME"] + "/bin:" + os.path.expanduser("~/.local/share/mise/shims")
                   + ":" + os.path.expanduser("~/.cargo/bin") + ":" + env.get("PATH", ""))

    print("\n########## %s ##########" % lang)
    print("命令:", " ".join(cmd), "| 端口:", port)
    free_port(port)
    with open(log, "a") as lf:
        proc = subprocess.Popen(cmd, cwd=d, env=env, stdout=lf, stderr=subprocess.STDOUT,
                                start_new_session=True)
    try:
        if not wait_listen(port, 90):
            print("FAIL: %d 未监听" % port)
            return False
        time.sleep(2)  # 等信号处理器注册
        result: dict = {}
        t = threading.Thread(target=fire_long_task, args=(port, result))
        t.start()
        time.sleep(1.2)  # 让请求进入处理中
        pid = listener_pid(port)
        print("listener pid=%s，在途 1 个 long-task，发送 SIGTERM" % pid)
        os.kill(pid, signal.SIGTERM)
        rel = wait_release(port, 30)
        t.join(timeout=15)
        time.sleep(0.5)
        txt = open(log).read()
        low = txt.lower()
        has_ok = any(m in low for m in OK_MARKERS)
        bad = [m for m in BAD_MARKERS if m in low]

        print("端口释放: %s" % ("%.2fs" % rel if rel >= 0 else "FAIL(30s 未释放)"))
        if result.get("ok"):
            print("在途请求: HTTP %s，耗时 %.2fs，body=%s"
                  % (result["status"], result["elapsed"], result["body"]))
        else:
            print("在途请求: 失败 %s（耗时 %.2fs）" % (result.get("error"), result["elapsed"]))
        print("关闭完成标记:", has_ok, "| 崩溃特征:", bad or "无")

        reasons = []
        if rel < 0:
            reasons.append("端口未释放")
        if not result.get("ok"):
            reasons.append("在途请求被打断（未拿到响应）")
        if not has_ok:
            reasons.append("缺少关闭完成标记")
        if bad:
            reasons.append("崩溃特征: %s" % ",".join(bad))
        print("结论:", "PASS" if not reasons else "FAIL -> " + "; ".join(reasons))
        return not reasons
    finally:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            pass
        subprocess.run(["pkill", "-9", "-f", "12-graceful-shutdown/" + lang],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)


def main() -> None:
    args = sys.argv[1:]
    if args and args[0] in CMDS:
        ok = check_lang(args[0], args[1] if len(args) > 1 else None)
        print("\n===== 总体: %s =====" % ("PASS" if ok else "FAIL"))
        return
    results = {}
    for lang in ("java", "go", "python", "rust", "ts-node"):
        results[lang] = check_lang(lang)
    print("\n===== 汇总 =====")
    for k, v in results.items():
        print("  %-8s %s" % (k, "PASS" if v else "FAIL"))
    print("总体:", "PASS" if all(results.values()) else "FAIL")


if __name__ == "__main__":
    main()
