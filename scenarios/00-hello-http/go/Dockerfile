# scenarios/00-hello-http/go — Go 1.22 标准库 net/http
# 监听端口 8081 ｜ 契约：GET /hello?name={xxx} → {"msg":"hello {xxx}"}

# ---------- 构建阶段 ----------
FROM golang:1.22-alpine AS build
WORKDIR /build

COPY go.mod ./
COPY main.go ./

# CGO_ENABLED=0 产出静态二进制，才能跑在 alpine / distroless 等无 glibc 的基础镜像上
# -trimpath 去掉构建路径，-ldflags="-s -w" 去掉符号表与 DWARF，显著减小体积
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /build/hello-http .

# ---------- 运行阶段 ----------
FROM alpine:3.20

# 非 root 运行：容器安全的默认要求
RUN addgroup -S app && adduser -S app -G app

WORKDIR /app
COPY --from=build /build/hello-http /app/hello-http
USER app

EXPOSE 8081
ENTRYPOINT ["/app/hello-http"]
