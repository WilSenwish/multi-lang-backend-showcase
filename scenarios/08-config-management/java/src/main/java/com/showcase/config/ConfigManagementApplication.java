package com.showcase.config;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigManagementApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConfigManagementApplication.class, args);
    }
}
