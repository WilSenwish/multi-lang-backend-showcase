# 场景 15：结构化并发 + 取消传播 ⭐

> **边界场景**：本场景刻意选一个"某些语言天生不擅长"的问题，用来回答技术选型里最关键的一问 ——
> **什么时候某门语言根本不该上场，补救方案又要付出多少代价。**

## 业务描述

一个请求扇出 N 个并发子任务（模拟"并行调用 N 个下游"），要求三条语义：

1. **取消传播（fail-fast）**：任一子任务失败 → 所有兄弟任务立即停止，**不等它们跑完**；
2. **超时取消**：父作用域 deadline 到期 → 全部子任务取消；
3. **结构化收尾**：作用域退出时，所有子任务必须已经结束 —— 不允许"请求已返回、任务还在后台跑"。

这三条听起来都像"理所当然"，但它们分别对应三件不同的事：
**作用域的生命周期**（结构化）、**取消信号如何到达子任务**（传播）、**子任务如何响应**（协作式检查点）。
五门语言对这三件事的支持程度差别很大 —— 这就是本场景要量化的东西。

### 为什么必须做契约级判定

上面三条语义**没有任何一条**能通过"端口通了 / 返回 200"发现：

- 取消没传播 → 服务照样返回 `outcome=failed`，只是 `completed` 里多塞了几个 id、`elapsed_ms` 变成"跑满"的量级；
- 任务没真正终止 → 请求照样返回，只是后台多了一堆僵尸任务（要靠"返回后过一会儿再看活跃数"才能发现）。

所以本场景的判定是**契约级**的：验证器对三个用例的 `outcome / completed / cancelled / failed / leaked`
逐字段比对，并对 `elapsed_ms` 设上下界，最后再做一次**延迟检查**（请求返回 3 秒后再查 `/stats`）。

## 统一接口（五门语言逐字一致）

```bash
POST /fanout
Content-Type: application/json

{
  "tasks": 8,            # 子任务数，1~64（默认 6）
  "task_ms": 2000,       # 单个子任务"跑满"所需时间，1~10000（默认 300）
  "fail_index": 3,       # 哪个子任务会失败，-1 表示不失败（默认 -1）
  "fail_after_ms": 250,  # 该任务多久后失败（默认 100）
  "timeout_ms": 0        # 父作用域超时，0 表示不设（默认 0）
}

# 响应（200）
{
  "lang": "go",
  "tasks": 8, "task_ms": 2000, "fail_index": 3, "fail_after_ms": 250, "timeout_ms": 0,
  "outcome": "failed",              # ⭐ completed | failed | timeout
  "completed": [],                  # ⭐ 跑满的子任务 id（升序）
  "cancelled": [0,1,2,4,5,6,7],     # ⭐ 被取消的子任务 id（升序）
  "failed": 3,                      # ⭐ 失败的子任务 id（-1 表示无）
  "elapsed_ms": 252,                # ⭐ 契约字段：必须远小于 task_ms
  "leaked": 0                       # ⭐ 作用域退出时仍存活的子任务数，必须 0
}
```

```bash
GET /stats      # 累计计数 + 当前活跃子任务数（验证器用它做"取消真的生效"的延迟判定）
{ "lang": "go", "active_tasks": 0, "started": 18, "completed": 4, "cancelled": 13, "failed": 0 }
```

**`outcome` 的判定顺序**（五门语言一致）：有任务失败 → `failed`；否则有任务被取消 → `timeout`；否则 `completed`。

## 验证方式（三个用例 + 延迟检查）

```bash
python3 .wb_verify/verify_all.py 15
```

| 用例 | 请求 | 期望 |
|------|------|------|
| 全成功 | `tasks=4, task_ms=200` | `outcome=completed`，`completed=[0,1,2,3]`，`elapsed_ms ≥ 150` |
| fail-fast 取消传播 | `tasks=8, task_ms=2000, fail_index=3, fail_after_ms=250` | `outcome=failed`，`completed=[]`，`cancelled=[0,1,2,4,5,6,7]`，`elapsed_ms < 1500` |
| 父作用域超时 | `tasks=6, task_ms=2000, timeout_ms=300` | `outcome=timeout`，`cancelled=[0..5]`，`elapsed_ms < 1500` |

最后一步是**延迟检查**：三个用例跑完后再等 3 秒查 `/stats`，`active_tasks` 必须为 0 ——
这条用来抓"取消只是打个标记、任务其实还在后台跑完"的假实现。

2026-10-16 本机实测：五门语言**全部通过**，三个用例的服务端耗时分别在
**约 200ms / 约 250ms / 约 300ms**（对应 `task_ms=200`、`fail_after_ms=250`、`timeout_ms=300`），
离散度在几毫秒内 —— 说明取消都在"信号发出点"附近就生效了，没有一门语言等到任务跑满 2000ms。

> 耗时是量级参考，不是性能结论：跨机器不可比，验证器只对它做上下界约束，不做精确断言。
> 复现命令见上；数字会随机器负载漂移，但"远小于 task_ms"这个关系不变。

## 技术选型：谁在负责这三件事

| 语言 | 结构化原语 | 取消如何到达子任务 | 收尾保证 |
|------|-----------|------------------|---------|
| Go | `errgroup.WithContext` | `context` 沿调用树传递，一等公民 | `Wait()` 返回即所有 goroutine 已退出 |
| Python | `asyncio.TaskGroup` | `CancelledError`（语言级，失败/超时自动取消兄弟） | `async with` 退出即所有任务已收尾 |
| TS(Node) | 无（手写 `Promise.all` 收尾） | `AbortSignal`（标准协议，fetch/定时器都能消费） | 靠 `Promise.all` + abort 让任务提前 resolve |
| Rust | 无（`JoinSet` 只管收尾） | 自建 `watch` 广播 + 每个 `await` 点 `select!` | `JoinSet` drop 即 abort，join 完即全部结束 |
| Java | `StructuredTaskScope`（JDK 21 **preview**） | **没有取消信号**：作用域收尾时直接 `Thread.interrupt()` | `join()` / `close()` 保证所有子任务结束 |

## 关键对比：Java 的取消不是"传播"，是"中断"

这是本场景最值得记住的一条。我在实现时原本的判断是"`StructuredTaskScope` 不传播取消，
必须手写标志"，于是写了 `AtomicBoolean` + 轮询。为了验证这个判断，做了一组对照实验：

```bash
# 对照版：子任务改成"不检查取消标志、直接 Thread.sleep(task_ms)"，失败时也不置位标志
# 结果（tasks=8, task_ms=2000, fail_index=3, fail_after_ms=250）：
#   {"outcome":"failed","completed":[],"cancelled":[0,1,2,4,5,6,7],"failed":3,
#    "elapsed_ms":260,"leaked":0}
```

**去掉手写标志后行为完全一样**：elapsed 仍是 260ms 量级、兄弟任务照样提前退出、无泄漏。
原因不是"取消被传播了"，而是 —— **JDK 21 的 `StructuredTaskScope` 在收尾时会中断未完成的子任务线程**
（`Thread.interrupt()`），`Thread.sleep` 因此抛出 `InterruptedException` 提前结束。

于是 Java 的成本换了个形式，一共三条：

1. **取消没有"信号"，只有中断** —— 拿不到取消原因，也没法像 `ctx.Err()` / `signal.reason` 那样检查；
2. **中断只对可中断的阻塞点生效** —— 不可中断的忙循环、部分阻塞 IO 下它会静默失效，
   此时仍需手写标志兜底（本实现保留了这条路径，并在 `catch (InterruptedException)` 处统一归一化成 `cancelled`）；
3. **`StructuredTaskScope` 到 JDK 21 仍是 preview** —— 编译与运行都要 `--enable-preview`，
   且 API 在 JDK 21 → 23 → 24 三度变更（JEP 453 / 480 / 487），生产落地通常只能用
   `ExecutorService` + `Future.cancel`，语义更弱一档。

其余四门语言的传播机制都是**显式的协作信号**，代价是在每个等待点都要写一次：

```go
select { case <-t.C: /* 完成 */ case <-ctx.Done(): /* 取消 */ }   // Go
```

```rust
tokio::select! { _ = sleep => Ok(()), _ = cancel.changed() => Err(()) }   // Rust
```

```python
await asyncio.sleep(...)   # 被取消时抛 CancelledError，捕获后记录状态再抛出
```

```ts
signal.addEventListener("abort", ...)   // Node
```

## 什么时候选谁

- **扇出聚合、下游多、必须 fail-fast** → Go（`context` 是这一套语义的最完整实现）/ Python（TaskGroup 语言级）
- **Node 全栈、已有 fetch 体系** → `AbortSignal` 够用，但要接受"结构化收尾得自己写"
- **Rust** → 显式、可控、无 GC 干扰，代价是每个 `await` 点都要记得 `select!` 取消分支（漏一个就是"取消不生效"）
- **Java** → 短期用 `ExecutorService` + `Future.cancel`；想上 `StructuredTaskScope` 就要接受
  preview API 的升级风险，并且明确"取消 = 线程中断"这一隐含语义

## 启动方式

| 语言 | 命令 | 端口 |
|------|------|------|
| Java | `cd java && mvn spring-boot:run`（**需 JDK 21**） | 8145 |
| Go | `cd go && go run .` | 8146 |
| Python | `cd python && pip install -r requirements.txt && uvicorn main:app --port 8147` | 8147 |
| Rust | `cd rust && cargo run` | 8148 |
| TS(Node) | `cd ts-node && npm install && npm run dev` | 8149 |

```bash
curl -X POST localhost:8146/fanout -H 'Content-Type: application/json' \
  -d '{"tasks":8,"task_ms":2000,"fail_index":3,"fail_after_ms":250}'
curl localhost:8146/stats
```

> **Java 的 JDK 21 从哪来**：本仓库顶层 `mise.toml` 固定的是 `zulu-17`，
> `scenarios/15-structured-concurrency/java/.mise.toml` 做了目录级覆盖（进入该目录自动切到 `zulu-21`）。
> 验证器里同样只对这一个场景的 Java 覆盖 `JAVA_HOME`（`env_for()`），其它场景不受影响。

## 已知坑（实测记录）

- **Spring Boot 的宽松绑定会把 `SERVER__PORT` 吃掉**：某些运行环境（含本仓库的验证沙箱）会注入
  `SERVER__PORT=49817`，它会被绑定成 `server.port`，把 `application.properties` 里的端口顶掉 ——
  排查"服务起了但端口不对"时先 `env | grep -i server`。验证器已在 `ENV` 里清掉这组变量。
- **XML 注释里不能出现连续两个连字符**：`pom.xml` 里写"必须带 `--enable-preview`"会让 Maven 直接报
  `Non-parseable POM`。这类注释要么改写成"开启 enable-preview 开关"，要么放进 `<description>`。
- **Rust 的 `JoinSet::join_next()` 返回的是"完成顺序"**，不是按下标 —— 结果必须按任务 id 落位，
  直接 `outcomes.push()` 会让 id 与结果错位（这个 bug 在"全成功"用例下看不出来，只有取消场景才暴露）。
