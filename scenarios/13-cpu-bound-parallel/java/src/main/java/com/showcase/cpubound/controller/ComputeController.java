package com.showcase.cpubound.controller;

import com.showcase.cpubound.dto.ComputeRequest;
import com.showcase.cpubound.dto.ComputeResponse;
import com.showcase.cpubound.service.ComputeService;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

/**
 * 场景 13：CPU 密集并行计算 — 控制器
 *
 * <p>只做参数接收与转发，业务逻辑在 {@link ComputeService}。
 */
@RestController
public class ComputeController {

    private final ComputeService computeService;

    public ComputeController(ComputeService computeService) {
        this.computeService = computeService;
    }

    /**
     * 触发一次 CPU 密集的并行计算。
     *
     * <p>请求体可省略（全部走缺省值）；缺省 task_count=8、iterations=2000000、concurrency=4。
     */
    @PostMapping("/compute")
    public ComputeResponse compute(@RequestBody(required = false) ComputeRequest req) {
        return computeService.run(req == null ? new ComputeRequest() : req);
    }
}
