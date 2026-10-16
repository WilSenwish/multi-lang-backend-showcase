package com.showcase.concurrency.controller;

import com.showcase.concurrency.dto.FanoutRequest;
import com.showcase.concurrency.dto.FanoutResponse;
import com.showcase.concurrency.dto.StatsResponse;
import com.showcase.concurrency.service.FanoutService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import java.util.LinkedHashMap;
import java.util.Map;

@RestController
public class FanoutController {

    private final FanoutService service;

    public FanoutController(FanoutService service) {
        this.service = service;
    }

    @GetMapping("/health")
    public Map<String, String> health() {
        Map<String, String> m = new LinkedHashMap<>();
        m.put("service", "structured-concurrency");
        m.put("lang", "java");
        m.put("engine", "StructuredTaskScope(ShutdownOnFailure) + 手写取消标志");
        return m;
    }

    @GetMapping("/stats")
    public StatsResponse stats() {
        return service.stats();
    }

    @PostMapping("/fanout")
    public ResponseEntity<?> fanout(@RequestBody(required = false) FanoutRequest req) {
        FanoutRequest r = req == null ? new FanoutRequest(null, null, null, null, null) : req;
        int tasks = r.tasks() == null ? 6 : r.tasks();
        int taskMs = r.taskMs() == null ? 300 : r.taskMs();
        int failIndex = r.failIndex() == null ? -1 : r.failIndex();
        int failAfterMs = r.failAfterMs() == null ? 100 : r.failAfterMs();
        int timeoutMs = r.timeoutMs() == null ? 0 : r.timeoutMs();

        String err = validate(tasks, taskMs, failIndex, failAfterMs, timeoutMs);
        if (err != null) {
            return ResponseEntity.badRequest().body(Map.of("error", err));
        }
        return ResponseEntity.ok(service.fanout(r));
    }

    /** 参数校验（与其它四门语言的取值范围逐字一致）。 */
    private String validate(int tasks, int taskMs, int failIndex, int failAfterMs, int timeoutMs) {
        if (tasks < 1 || tasks > 64) {
            return "tasks must be in [1, 64]";
        }
        if (taskMs < 1 || taskMs > 10_000) {
            return "task_ms must be in [1, 10000]";
        }
        if (failIndex < -1 || failIndex >= tasks) {
            return "fail_index must be in [-1, tasks)";
        }
        if (failAfterMs < 0 || failAfterMs > 10_000) {
            return "fail_after_ms must be in [0, 10000]";
        }
        if (timeoutMs < 0 || timeoutMs > 10_000) {
            return "timeout_ms must be in [0, 10000]";
        }
        return null;
    }
}
