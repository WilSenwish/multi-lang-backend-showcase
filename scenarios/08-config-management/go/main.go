package main

import (
	"fmt"
	"os"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/spf13/viper"
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
)

// ==================== zap 结构化日志初始化 ====================

// logger 全局 SugaredLogger（JSON 输出 + stdout + DEBUG 级别 + caller 信息）
var logger *zap.SugaredLogger

func init() {
	cfg := zap.NewProductionConfig()
	cfg.OutputPaths = []string{"stdout"}
	cfg.ErrorOutputPaths = []string{"stderr"}
	cfg.EncoderConfig.TimeKey = "time"
	cfg.EncoderConfig.LevelKey = "level"
	cfg.EncoderConfig.MessageKey = "msg"
	cfg.EncoderConfig.CallerKey = "caller"
	cfg.EncoderConfig.EncodeTime = zapcore.ISO8601TimeEncoder
	cfg.EncoderConfig.EncodeLevel = zapcore.LowercaseLevelEncoder
	cfg.EncoderConfig.EncodeCaller = zapcore.ShortCallerEncoder
	cfg.Level = zap.NewAtomicLevelAt(zapcore.DebugLevel) // 最低 DEBUG 级别
	cfg.Sampling = nil                                    // 关闭采样，保证 bench 等场景日志完整

	l, err := cfg.Build()
	if err != nil {
		panic(fmt.Sprintf("zap init failed: %v", err))
	}
	logger = l.Sugar()
}

// 场景 08：多环境配置管理 — Go 实现（viper）
//
// Go 配置管理特点：
// 1. viper 是 Go 生态事实标准（支持 yaml/json/toml/env flag 等）
// 2. SetConfigName + SetConfigPaths 自动找配置文件
// 3. SetEnvPrefix("MYAPP") + AutomaticEnv() 让 MYAPP_SERVER_PORT 自动覆盖
// 4. viper.Unmarshal 把配置 map 映射到结构体
// 5. Go 没有注解（Java @Validated / Python pydantic），手动校验
//
// 和 Java 对比：
// - Go 没有自动校验（手动 Validate()）
// - viper 支持配置热重载（WatchConfig）
// - env key replacer：MYAPP_DATABASE_POOL_SIZE → database.pool_size

const listenAddr = ":8111"

// ==================== 配置结构体 ====================

type ServerConfig struct {
	Port int    `mapstructure:"port" json:"port"`
	Host string `mapstructure:"host" json:"host"`
}

type DatabaseConfig struct {
	URL      string `mapstructure:"url" json:"url"`
	User     string `mapstructure:"user" json:"user"`
	Password string `mapstructure:"password" json:"-"` // 不输出
	PoolSize int    `mapstructure:"pool_size" json:"pool_size"`
}

type LoggingConfig struct {
	Level string `mapstructure:"level" json:"level"`
	JSON  bool   `mapstructure:"json" json:"json"`
}

type AppConfig struct {
	Server   ServerConfig   `mapstructure:"server" json:"server"`
	Database DatabaseConfig `mapstructure:"database" json:"database"`
	Logging  LoggingConfig  `mapstructure:"logging" json:"logging"`
	Env      string         `json:"env"`
	Source   string         `json:"source"`
}

// Validate 手动校验（Go 没有注解校验，启动时 fail-fast）
func (c *AppConfig) Validate() error {
	if c.Server.Port < 1 || c.Server.Port > 65535 {
		return fmt.Errorf("server.port 必须在 1-65535 之间，当前: %d", c.Server.Port)
	}
	if c.Server.Host == "" {
		return fmt.Errorf("server.host 不能为空")
	}
	if c.Database.URL == "" {
		return fmt.Errorf("database.url 不能为空")
	}
	if c.Database.User == "" {
		return fmt.Errorf("database.user 不能为空")
	}
	if c.Database.PoolSize < 1 || c.Database.PoolSize > 100 {
		return fmt.Errorf("database.pool_size 必须在 1-100 之间，当前: %d", c.Database.PoolSize)
	}
	validLevels := []string{"TRACE", "DEBUG", "INFO", "WARN", "ERROR"}
	level := strings.ToUpper(c.Logging.Level)
	ok := false
	for _, l := range validLevels {
		if l == level {
			ok = true
			break
		}
	}
	if !ok {
		return fmt.Errorf("logging.level 无效: %s，必须是 TRACE|DEBUG|INFO|WARN|ERROR", c.Logging.Level)
	}
	return nil
}

// ==================== 加载配置 ====================

func loadConfig() (*AppConfig, error) {
	v := viper.New()

	// 基础配置：config.yaml
	v.SetConfigName("config")
	v.SetConfigType("yaml")
	v.AddConfigPath(".")        // 当前目录
	v.AddConfigPath("./config") // config 子目录

	// 多环境：MYAPP_ENV=prod 则读 config-prod.yaml
	env := os.Getenv("MYAPP_ENV")
	if env != "" {
		v.SetConfigName("config-" + env)
	}

	// 环境变量前缀（MYAPP_SERVER_PORT 自动覆盖 server.port）
	v.SetEnvPrefix("MYAPP")
	v.SetEnvKeyReplacer(strings.NewReplacer(".", "_")) // . → _
	v.AutomaticEnv()

	// 设置默认值（fallback）
	v.SetDefault("server.port", 8111)
	v.SetDefault("server.host", "0.0.0.0")
	v.SetDefault("database.url", "localhost:3306")
	v.SetDefault("database.user", "admin")
	v.SetDefault("database.password", "secret")
	v.SetDefault("database.pool_size", 10)
	v.SetDefault("logging.level", "INFO")
	v.SetDefault("logging.json", true)

	// 读配置文件（文件不存在不报错，用默认值）
	if err := v.ReadInConfig(); err != nil {
		if _, ok := err.(viper.ConfigFileNotFoundError); !ok {
			return nil, fmt.Errorf("配置文件读取失败: %w", err)
		}
		logger.Debugw("配置文件未找到，使用默认值 + 环境变量")
	}

	// 解析到结构体
	var cfg AppConfig
	if err := v.Unmarshal(&cfg); err != nil {
		return nil, fmt.Errorf("配置解析失败: %w", err)
	}

	cfg.Env = env
	cfg.Source = "viper + config.yaml + MYAPP_ env"

	// 启动时校验
	if err := cfg.Validate(); err != nil {
		return nil, fmt.Errorf("配置校验失败: %w", err)
	}

	return &cfg, nil
}

// ==================== Handler ====================

var globalConfig *AppConfig

func configHandler(c *gin.Context) {
	// 响应专用结构体：不能直接用 DatabaseConfig —— 它的 Password 带 `json:"-"`，
	// 会把脱敏值一起吞掉（响应里直接少了 password 键，与其他四门语言不一致）。
	type DatabaseResp struct {
		URL      string `json:"url"`
		User     string `json:"user"`
		Password string `json:"password"`
		PoolSize int    `json:"pool_size"`
	}

	// 脱敏密码
	type RespConfig struct {
		Server   ServerConfig  `json:"server"`
		Database DatabaseResp  `json:"database"`
		Logging  LoggingConfig `json:"logging"`
		Env      string        `json:"env"`
		Source   string        `json:"source"`
	}
	resp := RespConfig{
		Server:   globalConfig.Server,
		Logging:  globalConfig.Logging,
		Env:      globalConfig.Env,
		Source:   globalConfig.Source,
	}
	resp.Database = DatabaseResp{
		URL:      globalConfig.Database.URL,
		User:     globalConfig.Database.User,
		Password: "********", // 脱敏
		PoolSize: globalConfig.Database.PoolSize,
	}

	c.JSON(200, resp)
}

// ==================== main ====================

func main() {
	defer logger.Sync() // flush 日志

	// 打印 env 覆盖示例（给用户看的帮助文字，保留 fmt.Println）
	fmt.Println("环境变量覆盖示例：")
	fmt.Println("  MYAPP_SERVER_PORT=9000 MYAPP_DATABASE_URL=prod-db:3306 go run main.go")
	fmt.Println("")

	cfg, err := loadConfig()
	if err != nil {
		logger.Fatalw("配置加载失败", "error", err)
	}
	globalConfig = cfg

	logger.Infow("配置加载成功", "env", cfg.Env, "port", cfg.Server.Port, "db", cfg.Database.URL)

	r := gin.Default() // 自带 Recovery + Logger 中间件
	r.GET("/config", configHandler)

	logger.Infow("server starting", "addr", listenAddr)
	if err := r.Run(listenAddr); err != nil {
		logger.Fatalw("server failed", "error", err)
	}
}
