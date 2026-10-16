package com.showcase.concurrency.dto;

import java.util.List;

/**
 * 扇出响应（字段与其它四门语言逐字一致）。
 *
 * @param outcome   completed | failed | timeout
 * @param completed 正常跑满的子任务 id（升序）
 * @param cancelled 被取消的子任务 id（升序）
 * @param failed    失败的子任务 id（-1 表示无）
 * @param leaked    作用域退出时仍在运行的子任务数（结构化保证 = 0）
 */
public record FanoutResponse(
        String lang,
        int tasks,
        int taskMs,
        int failIndex,
        int failAfterMs,
        int timeoutMs,
        String outcome,
        List<Integer> completed,
        List<Integer> cancelled,
        int failed,
        long elapsedMs,
        long leaked
) {
}
