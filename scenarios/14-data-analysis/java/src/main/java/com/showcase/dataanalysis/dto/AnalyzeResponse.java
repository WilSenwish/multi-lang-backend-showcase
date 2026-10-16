package com.showcase.dataanalysis.dto;

import lombok.AllArgsConstructor;
import lombok.Data;

import java.util.List;

@Data
@AllArgsConstructor
public class AnalyzeResponse {
    private int rows;
    private int categories;
    private List<GroupStat> groups;
    private List<TopRow> top10;
    private long genMs;
    private long aggMs;
    private long elapsedMs;
}
