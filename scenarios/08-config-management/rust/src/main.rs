//! 场景 08：多环境配置管理 — Rust 实现（config crate）
//!
//! Rust 配置管理特点（**和其他语言最大的差异点**）：
//!
//! 1. **编译期 embed 配置**：用 include_str! 把默认配置打进二进制
//!    其他语言（Java/Go/Python/TS）都需要运行时读文件
//!
//! 2. **配置校验时机**：Rust 结构体 #[derive(Deserialize)] 编译期生成反序列化代码，
//!    字段类型错误直接编译报错。但具体值校验（port 范围等）还是启动时。
//!
//! 3. **config crate**：支持 yaml + env 多来源按层级合并 + 覆盖
//!    SetEnvironment 让 MYAPP_SERVER__PORT 自动覆盖 server.port
//!    （config crate 默认用 __ 分隔，和其他语言的 _ 不同）
//!
//! 4. **Figment（figment crate）**：更灵活的覆盖模型（可选）
//!
//! 5. **错误处理**：ConfigError 枚举覆盖所有错误场景

use axum::{
    extract::State,
    response::IntoResponse,
    routing::get,
    Router,
};
use config::{Config, ConfigError, Environment, File};
use serde::{Deserialize, Serialize};
use std::sync::Arc;

// ==================== 配置结构体（derive Deserialize，编译期安全） ====================

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ServerConfig {
    pub port: u16,
    pub host: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct DatabaseConfig {
    pub url: String,
    pub user: String,
    pub password: String,
    pub pool_size: u16,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct LoggingConfig {
    #[serde(rename = "level")]
    pub level: String,
    pub json: bool,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct AppConfig {
    pub server: ServerConfig,
    pub database: DatabaseConfig,
    pub logging: LoggingConfig,
    // env / source 由 load_config 在反序列化后填充，配置源里没有，故加 default
    #[serde(default)]
    pub env: String,
    #[serde(default)]
    pub source: String,
}

impl AppConfig {
    /// 启动时校验（值的范围/非空，类型安全由 Rust 编译器保证）
    pub fn validate(&self) -> Result<(), String> {
        if self.server.port == 0 {
            return Err("server.port 不能为 0".into());
        }
        if self.server.host.is_empty() {
            return Err("server.host 不能为空".into());
        }
        if self.database.url.is_empty() {
            return Err("database.url 不能为空".into());
        }
        if self.database.user.is_empty() {
            return Err("database.user 不能为空".into());
        }
        if self.database.pool_size == 0 || self.database.pool_size > 100 {
            return Err(format!("database.pool_size 必须在 1-100 之间，当前: {}", self.database.pool_size));
        }
        let valid = ["TRACE", "DEBUG", "INFO", "WARN", "ERROR"];
        if !valid.contains(&self.logging.level.as_str()) {
            return Err(format!("logging.level 无效: {}", self.logging.level));
        }
        Ok(())
    }
}

// ==================== 加载配置 ====================

fn load_config() -> Result<AppConfig, ConfigError> {
    let env = std::env::var("MYAPP_ENV").unwrap_or_default();

    let mut builder = Config::builder();

    // 1. 默认值（编译期 embed？这里演示运行时 config.yaml）
    //    Rust 也可以 include_str! 把默认配置 embed，但这里保持和其他语言一致用文件
    builder = builder.add_source(File::with_name("config").required(false));

    // 2. 多环境覆盖：config-dev.yaml / config-prod.yaml
    if !env.is_empty() {
        builder = builder.add_source(File::with_name(&format!("config-{}", env)).required(false));
    }

    // 3. 环境变量覆盖（MYAPP_ 前缀，__ 分隔层级）
    //    MYAPP_DATABASE__URL=prod-db:3306 → database.url = "prod-db:3306"
    //    ⚠️ config 0.14 的两个默认值陷阱（README 曾误写"config crate 默认 __"）：
    //      a) 路径分隔符默认是**空串**（不是 "__"）—— 不显式 separator("__") 时，
    //         MYAPP_DATABASE__URL 会被当成单个键 "database__url"，永远匹配不上 database.url，
    //         且**不报错**，表现为"env 覆盖静默失效"；
    //      b) 一旦设置了 separator("__")，前缀分隔符会跟着变成 "__"（prefix_pattern = "myapp__"），
    //         导致 MYAPP_ 开头的键全部被跳过 —— 必须同时把 prefix_separator 钉回 "_"。
    builder = builder.add_source(
        Environment::with_prefix("MYAPP")
            .prefix_separator("_")
            .separator("__")
            .try_parsing(true), // 自动解析 int/bool/string
    );

    let config = builder.build()?;

    let mut cfg: AppConfig = config.try_deserialize()?;

    cfg.env = env;
    cfg.source = "config crate + config.yaml + MYAPP_ env (__ 分隔)".to_string();

    Ok(cfg)
}

// ==================== Handler ====================

type SharedState = Arc<AppConfig>;

async fn config_handler(State(cfg): State<SharedState>) -> impl axum::response::IntoResponse {
    use serde_json::json;

    // 脱敏密码
    let resp = json!({
        "server": {
            "port": cfg.server.port,
            "host": cfg.server.host,
        },
        "database": {
            "url": cfg.database.url,
            "user": cfg.database.user,
            "password": "********",
            "pool_size": cfg.database.pool_size,
        },
        "logging": {
            "level": cfg.logging.level,
            "json": cfg.logging.json,
        },
        "env": cfg.env,
        "source": cfg.source,
    });

    axum::Json(resp).into_response()
}

// ==================== main ====================

#[tokio::main]
async fn main() {
    // 初始化 tracing 日志：JSON 格式 + 最低 DEBUG 级别 + stdout
    tracing_subscriber::fmt()
        .with_env_filter(tracing_subscriber::EnvFilter::try_from_default_env()
            .unwrap_or_else(|_| "debug".into()))
        .with_target(false)
        .json()
        .init();

    tracing::debug!("env var example:");
    tracing::debug!("  MYAPP_SERVER__PORT=9000 MYAPP_DATABASE__URL=\"prod-db:3306\" cargo run");
    tracing::debug!("  (note: Rust config crate uses __ double underscore for level separator)");

    let cfg = match load_config() {
        Ok(c) => c,
        Err(e) => {
            tracing::error!(error = %e, "config load failed");
            std::process::exit(1);
        }
    };

    if let Err(e) = cfg.validate() {
        tracing::error!(error = %e, "config validation failed");
        std::process::exit(1);
    }

    tracing::info!(env = %cfg.env, port = cfg.server.port, db = %cfg.database.url, "config loaded successfully");

    let shared_cfg = Arc::new(cfg);
    let app = Router::new()
        .route("/config", get(config_handler))
        .with_state(shared_cfg.clone());

    let addr = "0.0.0.0:8113";
    tracing::info!(addr = %addr, "server starting");
    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    axum::serve(listener, app).await.unwrap();
}
