package com.showcase.dataanalysis.dto;

import lombok.AllArgsConstructor;
import lombok.Data;

@Data
@AllArgsConstructor
public class TopRow {
    private long id;
    private String category;
    private long amount;
}
