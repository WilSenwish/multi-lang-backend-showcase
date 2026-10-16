"""
场景 12：优雅关闭（Graceful Shutdown）— Python 实现（FastAPI）

Python 优雅关闭特点：
1. loop.add_signal_handler 注册信号处理器（SIGTERM/SIGINT）
2. asyncio.Event 作为关闭信号
3. FastAPI lifespan context 管理资源（yield 之后即关闭阶段）
4. uvicorn 内置 timeout_graceful_shutdown 参数

和 Go 对比：
- Go 用 signal.NotifyContext（context 风格），Python 用信号回调 + asyncio.Event
- Go 更简洁优雅；Python 也能做到
- Python asyncio 单线程天然避免并发竞争

测试：kill -TERM <pid>

实现要点（容易踩坑）：
- 信号回调收到的 signum 是 **int**（信号编号），不是 signal.Signals 枚举，
  直接写 sig.name 会抛 AttributeError；需要 signal.Signals(signum).name 转一下
- 信号处理器必须真正驱动 uvicorn 退出：仅把 asyncio.Event set() 掉并不会让服务停下。
  uvicorn 在 serve() 里用 signal.signal(sig, server.handle_exit) 注册了自己的处理器，
  所以这里先把它取出来（prev），打印日志后再交还给它 —— 这样无论用
  `python3 main.py` 还是 `uvicorn main:app` 启动都能走完标准优雅关闭流程，
  否则进程只能等外部 SIGKILL，优雅关闭就是假的
- 进程最终会被信号"补刀"结束：uvicorn 关闭收尾后会把原处理器还原并重新 raise 该信号
  （见 uvicorn/server.py capture_signals），因此进程退出码是 -15/143 而非 0，
  且 atexit 与未 flush 的 stdout 都不会执行 —— 日志要行缓冲或加 -u
"""
from __future__ import annotations

import asyncio
import signal
import sys

from fastapi import FastAPI
from fastapi.responses import JSONResponse

# 输出被重定向到文件时，stdout 默认是块缓冲；而进程在优雅关闭完成后会被信号直接终止
# （uvicorn 恢复信号默认处置，进程以 -15 退出，atexit 与缓冲区 flush 都不会执行），
# 未 flush 的缓冲会整块丢失。这里改成行缓冲，保证演示输出不会凭空消失。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)

# ==================== 全局状态 ====================

shutdown_event = asyncio.Event()
shutting_down = False
in_flight_count = 0
count_lock = asyncio.Lock()


def handle_signal(signum, _frame=None, prev=None):
    """信号处理器。

    注意两点：
    1. signum 是 int（信号编号）；signal.Signals(signum).name 才能拿到 'SIGTERM' 这类名字。
    2. 只 set() 事件并不会让服务退出：必须把信号交还给 uvicorn 自己的处理器，
       它才会置 should_exit 走标准优雅关闭流程。
    """
    try:
        name = signal.Signals(signum).name
    except ValueError:
        name = str(signum)
    print(f"\n[PYTHON] 收到信号: {name}")
    shutdown_event.set()
    if callable(prev):
        # prev 即 uvicorn 的 Server.handle_exit（uvicorn serve() 阶段用 signal.signal 注册的）
        prev(signum, _frame)


# ==================== Lifespan（FastAPI 启动/关闭钩子） ====================

async def lifespan(app: FastAPI):
    print("========================================")
    print("场景 12：优雅关闭 — Python 实现")
    print("信号：kill -TERM <pid> 或 Ctrl+C")
    print("========================================")

    # 信号处理器：注册到当前事件循环（覆盖 uvicorn 的注册，但把手势交还给它的处理器）
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        prev = signal.getsignal(sig)  # uvicorn 注册的 handle_exit（绑定方法）
        loop.add_signal_handler(sig, handle_signal, sig, None, prev)
    print("[PYTHON] 已注册 SIGTERM / SIGINT 处理器（信号将交还给 uvicorn 的关闭流程）")

    yield  # 启动服务

    # === 关闭阶段（yield 之后的代码）===
    global shutting_down
    shutting_down = True

    print("========================================")
    print("[GRACEFUL SHUTDOWN] Step 1/4: 标记 shutting_down=True")

    print("[GRACEFUL SHUTDOWN] Step 2/4: 停止接收新请求")
    # FastAPI/uvicorn 会自动处理

    print("[GRACEFUL SHUTDOWN] Step 3/4: 等待 in-flight 请求完成 (timeout=10s)")
    try:
        await asyncio.wait_for(wait_no_requests(), timeout=10.0)
        print("[GRACEFUL SHUTDOWN] ✅ 所有请求完成")
    except asyncio.TimeoutError:
        print(f"[GRACEFUL SHUTDOWN] ⚠️ 超时！还有 {in_flight_count} 个请求未完成")

    print("[GRACEFUL SHUTDOWN] Step 4/4: 释放资源")
    print("[GRACEFUL SHUTDOWN] ✅ Shutdown complete")
    print("========================================")


async def wait_no_requests():
    """轮询等待 in_flight_count 归零"""
    global in_flight_count
    while True:
        async with count_lock:
            current = in_flight_count
        if current == 0:
            return
        print(f"[GRACEFUL SHUTDOWN]   等待 {current} 个请求完成...")
        await asyncio.sleep(0.2)


app = FastAPI(title="graceful-shutdown-python", lifespan=lifespan)


# ==================== 端点 ====================

@app.get("/api/long-task")
async def long_task():
    global in_flight_count
    async with count_lock:
        in_flight_count += 1
        id_val = in_flight_count
    print(f"[REQUEST] 开始处理 long-task, id={id_val}, in-flight={in_flight_count}")

    try:
        await asyncio.sleep(3.0)
        print(f"[REQUEST] 完成 long-task, id={id_val}")
    finally:
        async with count_lock:
            in_flight_count -= 1

    return {"ok": True, "duration_ms": 3000, "shutting_down": shutting_down}


@app.get("/api/health")
async def health():
    body = {
        "service": "graceful-shutdown-python",
        "shutting_down": shutting_down,
        "in_flight": in_flight_count,
    }
    status = 503 if shutting_down else 200
    return JSONResponse(content=body, status_code=status)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8132,
        log_level="info",
        timeout_graceful_shutdown=10,  # uvicorn 优雅关闭超时 10s
    )
