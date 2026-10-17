package com.showcase.httpclient.config;

import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManager;
import org.apache.hc.core5.util.TimeValue;
import org.apache.hc.core5.util.Timeout;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * HTTP 客户端配置 — Java
 *
 * Java HTTP Client 特点：
 * 1. RestTemplate 同步，WebClient 异步（Spring 5+）
 * 2. Apache HttpClient 5 底层连接池：PoolingHttpClientConnectionManager
 * 3. 连接超时（connectTimeout）vs 读取超时（responseTimeout）分开配置
 * 4. Resilience4j 做熔断（AOP 拦截，业务代码无侵入）；重试在服务内手工指数退避
 *
 * 连接池模型：
 * - maxTotal（全局最大连接数，默认 25）
 * - maxPerRoute（每个主机最大连接数，默认 5）
 * - evictExpiredConnections + evictIdleConnections（自动回收空闲连接）
 *
 * ⚠️ 每次请求基于共享连接池新建 client：请求级 timeoutMs 需要逐请求设置
 * RequestConfig，而 HC5 的 RequestConfig 是 client 级默认值（Bean 里的 RestTemplate
 * 固定 3s/10s，导致请求体的 timeout_ms 被整个忽略）。新建 client 只是包一层
 * builder，连接仍走共享的 PoolingHttpClientConnectionManager。
 */
@Configuration
public class HttpClientConfig {

    @Bean
    public PoolingHttpClientConnectionManager connectionManager() {
        PoolingHttpClientConnectionManager cm = new PoolingHttpClientConnectionManager();
        cm.setMaxTotal(100);          // 全局最大连接数
        cm.setDefaultMaxPerRoute(20); // 每个主机最大连接数
        return cm;
    }

    /**
     * 基于共享连接池 + 逐请求超时，构造一个短生命周期 client。
     * 调用方用 try-with-resources 关闭。
     *
     * ⚠️ setConnectionManagerShared(true) 不能省：HC5 的 HttpClientBuilder 默认把
     * 外部注入的 manager 视为"归自己所有"，client.close() 会连带 shutdown() 整个
     * 连接池 —— 第一个请求成功后池子就废了，后续全部 "Connection pool shut down"。
     * 显式声明共享后，close() 只回收 client 自己创建的连接。
     */
    public static CloseableHttpClient buildClient(PoolingHttpClientConnectionManager cm, int timeoutMs) {
        RequestConfig requestConfig = RequestConfig.custom()
                .setConnectTimeout(Timeout.ofSeconds(3))                 // 建立连接超时
                .setResponseTimeout(Timeout.ofMilliseconds(timeoutMs))   // 读取响应超时（请求级）
                .build();

        return HttpClients.custom()
                .setConnectionManager(cm)
                .setConnectionManagerShared(true)
                .setDefaultRequestConfig(requestConfig)
                .evictExpiredConnections()
                .evictIdleConnections(TimeValue.ofSeconds(30))
                .build();
    }
}
