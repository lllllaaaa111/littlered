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
# 仅安装 Debian Bookworm (python:3.11-slim) 中确认存在的包：
#
# 移除原因：
#   fonts-noto-cjk  → slim 镜像 apt 源中不可用（包体积 ~200MB，需要额外源）
#   libgtk-3-0      → headless Chromium 不需要 GTK
#   libxss1         → X11 屏保扩展，headless 不需要
#   libxrender1     → headless 不需要
#   libxcursor1     → 鼠标光标，headless 不需要
#   libxi6          → X11 输入扩展，headless 不需要
#   libxtst6        → X11 测试扩展，headless 不需要
#
# libasound2t64 是 Bookworm 中 libasound2 的新名称（time_t 64位迁移）
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Chromium headless 核心运行时依赖
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
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    libasound2t64 \
    # 字体（基础拉丁 + 中文 fallback）
    fonts-liberation \
    fonts-noto \
    # 工具
    gettext-base \
    postgresql-client \
    redis-tools \
    curl \
    wget \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ── 安装 Python 依赖 ───────────────────────────────────────
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# ── 安装 Playwright Chromium 浏览器 ──────────────────────
# 注意：不执行 playwright install-deps，系统依赖已在上方 apt-get 步骤手动安装
RUN playwright install chromium

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
