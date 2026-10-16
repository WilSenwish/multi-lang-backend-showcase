package com.showcase.streaming.controller;

import com.showcase.streaming.dto.StreamRequest;
import com.showcase.streaming.dto.StreamResponse;
import com.showcase.streaming.service.StreamService;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class StreamController {

    private final StreamService service;

    public StreamController(StreamService service) {
        this.service = service;
    }

    @PostMapping("/stream/process")
    public StreamResponse process(@RequestBody(required = false) StreamRequest req) throws Exception {
        int sizeMb = clamp(req == null ? null : req.sizeMb(), 32, 1, 512);
        int chunkKib = clamp(req == null ? null : req.chunkKib(), 64, 1, 4096);
        int minAmount = clamp(req == null ? null : req.minAmount(), 50000, 0, 99999);
        return service.process(sizeMb, chunkKib, minAmount);
    }

    private static int clamp(Integer v, int dflt, int lo, int hi) {
        int x = v == null ? dflt : v;
        return Math.max(lo, Math.min(hi, x));
    }
}
