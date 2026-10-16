# scenarios/00-hello-http/ts-node — fastify 4 + zod
# 监听端口 8084 ｜ 契约：GET /hello?name={xxx} → {"msg":"hello {xxx}"}

# ---------- 构建阶段：tsc 产出 dist/main.js ----------
FROM node:24-alpine AS build
WORKDIR /build

# npm ci 严格按 package-lock.json 安装，保证与本地构建结果一致
COPY package.json package-lock.json ./
RUN npm ci

COPY tsconfig.json ./
COPY src ./src
RUN npm run build

# ---------- 运行阶段：只装生产依赖 ----------
FROM node:24-alpine
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force

COPY --from=build /build/dist ./dist

# node 官方镜像自带非 root 用户 node
USER node

EXPOSE 8084
CMD ["node", "dist/main.js"]
