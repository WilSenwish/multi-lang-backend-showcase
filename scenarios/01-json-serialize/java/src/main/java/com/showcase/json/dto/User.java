package com.showcase.json.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;

/**
 * 测试用嵌套结构：User -> Address + tags 数组 + scores 空数组
 *
 * Jackson 特点：
 * - 默认 null 值字段也会序列化（email: null）
 * - 可以用 @JsonInclude(Include.NON_NULL) 过滤
 * - 字段名默认和 Java 字段一致，@JsonProperty 可映射
 * - 空集合会输出 []（不是 null）
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class User {
    private int id;
    private String name;
    /** null 字段 — Jackson 默认会序列化出来 */
    private String email;
    private int age;
    private List<String> tags;
    private Address address;
    /** 空数组 — Jackson 输出 [] */
    private List<Integer> scores;

    /** 嵌套对象 */
    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class Address {
        @JsonProperty("city")
        private String city;
        @JsonProperty("zip")
        private String zip;
    }

    /** 构造测试用的 demo 对象 */
    public static User demo() {
        return User.builder()
                .id(1)
                .name("Alice")
                .email(null)
                .age(28)
                .tags(List.of("engineer", "java"))
                .address(Address.builder().city("Beijing").zip("100000").build())
                .scores(List.of())
                .build();
    }
}
