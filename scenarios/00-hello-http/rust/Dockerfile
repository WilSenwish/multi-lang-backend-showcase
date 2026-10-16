# scenarios/00-hello-http/rust — axum 0.7 + tokio
# 监听端口 8083 ｜ 契约：GET /hello?name={xxx} → {"msg":"hello {xxx}"}

# ---------- 构建阶段 ----------
FROM rust:1.82-bookworm AS build
WORKDIR /build

# Cargo.lock 被 .gitignore 忽略，故只拷贝 Cargo.toml。
# 先用一个空 main.rs 把依赖编译出来，让依赖层可被缓存（源码改动不会重编全部依赖）。
COPY Cargo.toml ./
RUN mkdir -p src \
    && echo "fn main() {}" > src/main.rs \
    && cargo build --release \
    && rm -rf src

COPY src ./src
# 强制重新编译真实源码（cargo 依赖 mtime，需 touch 以绕开缓存命中）
RUN touch src/main.rs && cargo build --release

# ---------- 运行阶段 ----------
FROM debian:bookworm-slim

RUN useradd --create-home --shell /bin/bash app

WORKDIR /app
COPY --from=build /build/target/release/hello-http /app/hello-http
RUN chown app:app /app/hello-http
USER app

EXPOSE 8083
ENTRYPOINT ["/app/hello-http"]
