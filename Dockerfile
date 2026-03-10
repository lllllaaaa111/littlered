# ============================================================
# 小红书自动运营 Agent — Dockerfile
# 基础镜像：python:3.11-slim (Debian Bookworm)
# ============================================================

FROM python:3.11-slim AS base

# ── 构建参数 ──────────────────────────────────────────────
ARG DEBIAN_FRONTEND=noninteractive
ARG PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# ── 环境变量 ──────────────────────────────────────────────
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# ── 安装系统依赖 ───────────────────────────────────────────
# Playwright Chromium 运行时依赖 + gettext(envsubst) + pg/redis 客户端
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Playwright / Chromium 依赖
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcairo2 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libexpat1 \
    libfontconfig1 \
    libgbm1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libpango-1.0-0 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxkbcommon0 \
    libxrandr2 \
    libxrender1 \
    libxss1 \
    libxtst6 \
    libasound2 \
    fonts-liberation \
    fonts-noto-cjk \
    # 工具
    gettext-base \
    postgresql-client \
    redis-tools \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/*

# ── 安装 Python 依赖 ───────────────────────────────────────
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# ── 安装 Playwright Chromium 浏览器 ──────────────────────
RUN playwright install chromium && \
    playwright install-deps chromium

# ── 复制应用代码 ───────────────────────────────────────────
COPY . .

# ── 创建运行时目录 ─────────────────────────────────────────
RUN mkdir -p \
    /app/storage/images \
    /app/storage/temp \
    /app/cookies \
    /app/logs \
    /app/chroma_data

# ── 复制并赋予执行权限给启动脚本 ──────────────────────────
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# ── 创建非 root 运行用户（安全最佳实践）────────────────────
RUN groupadd -r agent && useradd -r -g agent -d /app agent && \
    chown -R agent:agent /app /ms-playwright

USER agent

# ── 暴露端口 ──────────────────────────────────────────────
EXPOSE 8000

# ── 健康检查 ──────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# ── 启动入口 ──────────────────────────────────────────────
ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
