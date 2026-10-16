package com.showcase.dataanalysis.dto;

import lombok.AllArgsConstructor;
import lombok.Data;

@Data
@AllArgsConstructor
public class GroupStat {
    private String category;
    private long count;
    private long sum;
    private double avg;
    private long p50;
    private long p95;
}
