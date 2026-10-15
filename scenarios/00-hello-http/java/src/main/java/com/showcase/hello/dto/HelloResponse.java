package com.showcase.hello.dto;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * 统一响应 DTO
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
public class HelloResponse {
    private String msg;
}
