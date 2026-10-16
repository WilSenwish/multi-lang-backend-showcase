# scenarios/00-hello-http/java — Spring Boot 3.2.12 + JDK 17
# 监听端口 8080 ｜ 契约：GET /hello?name={xxx} → {"msg":"hello {xxx}"}

# ---------- 构建阶段：Maven 打 fat jar ----------
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /build

# 先只拷贝 pom 并解析依赖，源码变更时不会重复下载 Maven 依赖
COPY pom.xml ./
RUN mvn -B dependency:go-offline

COPY src ./src
RUN mvn -B clean package -DskipTests

# ---------- 运行阶段：仅保留 JRE 与 jar ----------
FROM eclipse-temurin:17-jre-jammy
WORKDIR /app

# Spring Boot repackage 产物为 target/hello-http-1.0.0.jar（*.jar 不会命中 .jar.original）
COPY --from=build /build/target/*.jar /app/app.jar

EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
