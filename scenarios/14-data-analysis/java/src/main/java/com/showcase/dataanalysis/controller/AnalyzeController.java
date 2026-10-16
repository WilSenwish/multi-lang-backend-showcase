package com.showcase.dataanalysis.controller;

import com.showcase.dataanalysis.dto.AnalyzeRequest;
import com.showcase.dataanalysis.dto.AnalyzeResponse;
import com.showcase.dataanalysis.service.AnalyzeService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/")
public class AnalyzeController {

    private final AnalyzeService service;

    public AnalyzeController(AnalyzeService service) {
        this.service = service;
    }

    @GetMapping("/health")
    public Map<String, String> health() {
        return Map.of("service", "data-analysis", "lang", "java", "engine", "tablesaw");
    }

    @PostMapping("/analyze")
    public AnalyzeResponse analyze(@RequestBody(required = false) AnalyzeRequest req) {
        return service.analyze(req != null ? req : new AnalyzeRequest());
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Map<String, String>> badRequest(IllegalArgumentException e) {
        return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
    }
}
