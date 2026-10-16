# scenarios/00-hello-http/python — FastAPI + uvicorn
# 监听端口 8082 ｜ 契约：GET /hello?name={xxx} → {"msg":"hello {xxx}"}

FROM python:3.11-slim

# 容器内禁止生成 .pyc，且输出不缓冲，保证日志能被 docker logs 实时收集
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 先只装依赖，requirements.txt 不变时复用该层缓存
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py ./

# 非 root 运行
RUN useradd --create-home --shell /bin/bash app && chown -R app:app /app
USER app

EXPOSE 8082

# 与本地 `uvicorn main:app --port 8082` 保持一致；host 必须是 0.0.0.0，
# 否则容器只监听 127.0.0.1，端口映射后外部访问不到
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8082"]
