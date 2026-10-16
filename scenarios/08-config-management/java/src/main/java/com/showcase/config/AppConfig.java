package com.showcase.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

/**
 * 统一配置对象 — Java 实现
 *
 * Java 配置管理特点：
 * 1. @ConfigurationProperties(prefix = "myapp") 自动绑定 yaml 到强类型对象
 * 2. @Validated + JSR-303 注解（@NotNull / @Min / @Pattern）启动时校验
 * 3. 校验失败 → Spring Boot 直接启动失败（fail-fast）
 * 4. 多环境：application-{profile}.yml + spring.profiles.active
 * 5. 环境变量覆盖：MYAPP_DATABASE_POOL-SIZE=30 自动生效（Spring Boot 规则）
 *
 * 和其他语言对比：
 * - Java 校验在启动时（和 Go/Python/Node 一样），但 Spring Boot 自动处理
 * - Rust config 宏可以把配置 embed 到二进制（编译期），其他语言不行
 * - Spring Boot 的宽松绑定规则（myapp.database.pool-size → poolSize）很方便
 */
@Validated
@ConfigurationProperties(prefix = "myapp")
public class AppConfig {

    @Valid
    @NotNull(message = "myapp.server 不能为空")
    private Server server = new Server();

    @Valid
    @NotNull(message = "myapp.database 不能为空")
    private Database database = new Database();

    @Valid
    @NotNull(message = "myapp.logging 不能为空")
    private Logging logging = new Logging();

    private String env = System.getenv().getOrDefault("MYAPP_ENV", "default");

    // ============ 嵌套配置类 ============

    public static class Server {
        @Min(value = 1, message = "端口最小值 1")
        @Max(value = 65535, message = "端口最大值 65535")
        private int port = 8080;

        @NotBlank(message = "host 不能为空")
        private String host = "0.0.0.0";

        // getter/setter
        public int getPort() { return port; }
        public void setPort(int port) { this.port = port; }
        public String getHost() { return host; }
        public void setHost(String host) { this.host = host; }
    }

    public static class Database {
        @NotBlank(message = "database.url 不能为空")
        private String url = "localhost:3306";

        @NotBlank(message = "database.user 不能为空")
        private String user = "admin";

        private String password = "secret";

        @Min(value = 1, message = "pool-size 最小值 1")
        @Max(value = 100, message = "pool-size 最大值 100")
        private int poolSize = 10;

        public String getUrl() { return url; }
        public void setUrl(String url) { this.url = url; }
        public String getUser() { return user; }
        public void setUser(String user) { this.user = user; }
        public String getPassword() { return password; }
        public void setPassword(String password) { this.password = password; }
        public int getPoolSize() { return poolSize; }
        public void setPoolSize(int poolSize) { this.poolSize = poolSize; }
    }

    public static class Logging {
        @Pattern(regexp = "TRACE|DEBUG|INFO|WARN|ERROR", message = "level 必须是 TRACE|DEBUG|INFO|WARN|ERROR")
        private String level = "INFO";

        private boolean json = true;

        public String getLevel() { return level; }
        public void setLevel(String level) { this.level = level; }
        public boolean isJson() { return json; }
        public void setJson(boolean json) { this.json = json; }
    }

    // ============ getter/setter ============

    public Server getServer() { return server; }
    public void setServer(Server server) { this.server = server; }
    public Database getDatabase() { return database; }
    public void setDatabase(Database database) { this.database = database; }
    public Logging getLogging() { return logging; }
    public void setLogging(Logging logging) { this.logging = logging; }
    public String getEnv() { return env; }
}
