package com.showcase.dataanalysis.dto;

import lombok.Data;

@Data
public class AnalyzeRequest {
    private Integer rows;
    private Integer categories;

    public int effectiveRows() {
        return rows != null ? rows : 200_000;
    }

    public int effectiveCategories() {
        return categories != null ? categories : 8;
    }
}
