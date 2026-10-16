package com.showcase.errors.advice;

import com.showcase.errors.dto.ErrorBody;
import com.showcase.errors.service.AppError;
import com.showcase.errors.service.ErrorState;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.ArrayList;
import java.util.List;

/**
 * 统一错误出口。
 *
 * <p>Java 的取舍：
 * <ul>
 *   <li>{@code @RestControllerAdvice} 把"错误 → 响应"的映射从业务代码里彻底抽走，
 *       业务方法里一个 try/catch 都不用写 —— 这是五门语言里最干净的一种分离。</li>
 *   <li>代价是**编译期不再知道某个控制器会抛什么**：checked exception 的强制声明
 *       在 Spring 这套"全抛出去"的写法面前形同虚设，漏一个 {@code @ExceptionHandler}
 *       分支就会退回默认的 500 HTML。</li>
 *   <li>异常自带调用栈（{@code getStackTrace()} 永远非空），代价是构造栈的开销 ——
 *       高并发下"用异常做控制流"是真实的性能问题。</li>
 * </ul>
 */
@RestControllerAdvice
public class GlobalExceptionHandler {

    private final ErrorState state;

    public GlobalExceptionHandler(ErrorState state) {
        this.state = state;
    }

    @ExceptionHandler(AppError.class)
    public ResponseEntity<ErrorBody> handleAppError(AppError ex, HttpServletRequest request) {
        state.noteHandled();
        return ResponseEntity.status(ex.httpStatus()).body(new ErrorBody(
                kindOf(request), ex.code(), ex.getMessage(), traceOf(request),
                causeChain(ex), ex.details(), false, false));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ErrorBody> handleUnexpected(Exception ex, HttpServletRequest request) {
        state.notePanic();
        String msg = String.valueOf(ex.getMessage());
        boolean stack = ex.getStackTrace() != null && ex.getStackTrace().length > 0;
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(new ErrorBody(
                "panic", "INTERNAL", msg, traceOf(request),
                causeChain(ex), List.of(), stack, true));
    }

    /** 沿 getCause() 收集消息：最外层 → 根因。 */
    private static List<String> causeChain(Throwable t) {
        List<String> out = new ArrayList<>();
        Throwable cur = t;
        while (cur != null && out.size() < 32) {
            out.add(String.valueOf(cur.getMessage()));
            cur = cur.getCause();
        }
        return out;
    }

    private static String traceOf(HttpServletRequest request) {
        Object v = request.getAttribute("traceId");
        return v == null ? "tid-unknown" : String.valueOf(v);
    }

    private static String kindOf(HttpServletRequest request) {
        String path = request.getRequestURI();
        int i = path.lastIndexOf('/');
        return i >= 0 ? path.substring(i + 1) : path;
    }
}
