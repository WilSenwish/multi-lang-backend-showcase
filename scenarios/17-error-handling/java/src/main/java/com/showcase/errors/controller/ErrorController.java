package com.showcase.errors.controller;

import com.showcase.errors.dto.ErrorBody;
import com.showcase.errors.dto.StatsBody;
import com.showcase.errors.service.AppError;
import com.showcase.errors.service.ErrorState;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.concurrent.CompletableFuture;

/**
 * 五种错误形态的入口。
 *
 * <p>本类**故意不写任何 try/catch**：所有错误都直接抛出去，由
 * {@link com.showcase.errors.advice.GlobalExceptionHandler} 统一转换成契约响应体 ——
 * 这正是 Java 生态里"错误处理与业务代码分离"的常规做法。
 */
@RestController
public class ErrorController {

    private final ErrorState state;

    public ErrorController(ErrorState state) {
        this.state = state;
    }

    @GetMapping("/errors/{kind}")
    public ResponseEntity<ErrorBody> errors(
            @PathVariable String kind,
            @RequestHeader(value = "X-Trace-Id", required = false) String traceHeader,
            HttpServletRequest request) {

        String traceId = (traceHeader == null || traceHeader.isBlank())
                ? "tid-" + state.nextSeq()
                : traceHeader;
        // 放进 request attribute，供 @ExceptionHandler 读取：
        // 异常对象本身不带 trace_id，跨层传递全靠这类"旁路"机制（MDC / ThreadLocal 同理）
        request.setAttribute("traceId", traceId);
        state.lastTraceId(traceId);

        switch (kind) {

            case "not_found":
                throw new AppError("NOT_FOUND", "user 42 not found", 404);

            case "validation":
                throw new AppError("VALIDATION_FAILED", "invalid request", 400,
                        List.of("email: required", "age: must be >= 0"));

            case "wrap_chain":
                throw buildChain();

            case "panic":
                // 未捕获异常：交给 GlobalExceptionHandler 兜底
                throw new RuntimeException("boom-17");

            case "async_detached":
                // ⭐ 深水区：CompletableFuture 里的异常**不会自动出现在任何地方** ——
                // 不 join/get、不写 whenComplete/exceptionally，它就静静地躺在 Future 里，
                // 直到有人 join 才以 ExecutionException 的形式炸出来（通常已经太晚了）。
                CompletableFuture.runAsync(() -> {
                    try {
                        Thread.sleep(120);
                    } catch (InterruptedException ignored) {
                        Thread.currentThread().interrupt();
                    }
                    throw new RuntimeException("async-boom-17");
                }, state.detachedPool).whenComplete((v, ex) -> {
                    if (ex != null) {
                        state.noteUnhandled(rootMessage(ex));
                    }
                });
                return ResponseEntity.status(HttpStatus.ACCEPTED).body(new ErrorBody(
                        "async_detached", "ACCEPTED", "async work spawned", traceId,
                        List.of(), List.of(), false, false));

            default: {
                String msg = "unknown kind: " + kind;
                return ResponseEntity.status(HttpStatus.NOT_FOUND).body(new ErrorBody(
                        kind, "UNKNOWN_KIND", msg, traceId, List.of(msg), List.of(), false, false));
            }
        }
    }

    /** 四层包装：db → repository → service → handler，每层都把 cause 挂上。 */
    private static AppError buildChain() {
        RuntimeException root = new RuntimeException("db: row 42 not found");
        AppError repo = new AppError("REPO", "repository: load user", 500, List.of(), root);
        AppError svc = new AppError("SERVICE", "service: get profile", 500, List.of(), repo);
        return new AppError("WRAPPED", "handler: GET /errors/wrap_chain", 500, List.of(), svc);
    }

    /** CompletionException 会把真实异常包一层，取消息时必须剥开。 */
    private static String rootMessage(Throwable t) {
        Throwable cur = t;
        while (cur.getCause() != null && cur != cur.getCause()) {
            cur = cur.getCause();
        }
        return String.valueOf(cur.getMessage());
    }

    @GetMapping("/stats")
    public StatsBody stats() {
        return new StatsBody(state.handled(), state.unhandled(), state.panics(),
                state.lastUnhandled(), state.lastTraceId());
    }
}
