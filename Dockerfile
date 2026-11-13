# Watchpost 核心镜像：API / watcher / collector 共用（纯标准库，无需 pip 安装）
# 构建：docker build -t ghcr.io/balareshe/watchpost-core:dev .
FROM python:3.12-alpine

LABEL org.opencontainers.image.title="Watchpost core" \
      org.opencontainers.image.description="Watchpost 状态页 / 事件工单 / 通知后端（API + watcher + collector）" \
      org.opencontainers.image.source="https://github.com/balareshe/watchpost" \
      org.opencontainers.image.licenses="LicenseRef-Watchpost-NC-1.0" \
      org.opencontainers.image.vendor="balareshe"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai

WORKDIR /app

COPY server/app.py server/watch.py /app/
COPY collector/collect.py /app/collect.py
COPY VERSION /app/VERSION

# api 与 watcher 需要写状态/数据（由 compose 挂载卷），这里只建目录
RUN mkdir -p /data /state /web/data

EXPOSE 8099
CMD ["python", "/app/app.py"]
