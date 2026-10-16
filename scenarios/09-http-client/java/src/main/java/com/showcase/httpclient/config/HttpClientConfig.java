package com.showcase.httpclient.config;

import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManager;
import org.apache.hc.core5.util.TimeValue;
import org.apache.hc.core5.util.Timeout;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.HttpComponentsClientHttpRequestFactory;
import org.springframework.web.client.RestTemplate;

import java.time.Duration;

/**
 * HTTP 客户端配置 — Java
 *
 * Java HTTP Client 特点：
 * 1. RestTemplate 同步，WebClient 异步（Spring 5+）
 * 2. Apache HttpClient 5 底层连接池：PoolingHttpClientConnectionManager
 * 3. 连接超时（connectTimeout）vs 读取超时（connectionRequestTimeout / socketTimeout）分开配置
 * 4. Resilience4j 做熔断/重试（AOP 拦截，业务代码无侵入）
 *
 * 连接池模型：
 * - maxTotal（全局最大连接数，默认 25）
 * - maxPerRoute（每个主机最大连接数，默认 5）
 * - evictExpiredConnections + evictIdleConnections（自动回收空闲连接）
 */
@Configuration
public class HttpClientConfig {

    @Bean
    public CloseableHttpClient httpClient() {
        // Apache HttpClient 5 连接池
        PoolingHttpClientConnectionManager cm = new PoolingHttpClientConnectionManager();
        cm.setMaxTotal(100);          // 全局最大连接数
        cm.setDefaultMaxPerRoute(20);  // 每个主机最大连接数

        // HC5 的请求级超时统一在 RequestConfig 配置。
        // 注意：Spring 6 的 HttpComponentsClientHttpRequestFactory 已移除
        // setReadTimeout/setResponseTimeout，读取超时必须由下层 responseTimeout 控制。
        RequestConfig requestConfig = RequestConfig.custom()
                .setConnectTimeout(Timeout.ofSeconds(3))      // 建立连接超时
                .setResponseTimeout(Timeout.ofSeconds(10))    // 读取响应超时
                .build();

        return HttpClients.custom()
                .setConnectionManager(cm)
                .setDefaultRequestConfig(requestConfig)
                .evictExpiredConnections()
                .evictIdleConnections(TimeValue.ofSeconds(30))
                .build();
    }

    @Bean
    public RestTemplate restTemplate(CloseableHttpClient httpClient) {
        // RestTemplate 用 Apache HttpClient 做底层
        HttpComponentsClientHttpRequestFactory factory =
                new HttpComponentsClientHttpRequestFactory(httpClient);
        // 连接超时 3s（读取超时由底层 RequestConfig.responseTimeout 控制）
        factory.setConnectTimeout(Duration.ofMillis(3000));

        return new RestTemplateBuilder()
                .requestFactory(() -> factory)
                .build();
    }
}
