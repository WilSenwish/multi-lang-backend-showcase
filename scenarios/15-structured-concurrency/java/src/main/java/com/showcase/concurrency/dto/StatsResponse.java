package com.showcase.concurrency.dto;

/**
 * /stats 响应：累计计数 + 当前活跃子任务数。
 * 验证器用它做"取消是否真的生效"的延迟判定 —— 若取消只是标记而任务仍在后台跑完，
 * active_tasks 在请求返回后的一段时间内就不会归零。
 */
public record StatsResponse(
        String lang,
        long activeTasks,
        long started,
        long completed,
        long cancelled,
        long failed
) {
}
