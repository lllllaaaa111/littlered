#!/bin/bash
# ============================================================
# Docker 容器启动脚本
# 职责：
#   1. 等待 PostgreSQL 就绪
#   2. 等待 Redis 就绪
#   3. 使用环境变量渲染 config.yaml
#   4. 启动应用程序
# ============================================================

set -e

# ── 颜色输出 ──────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[entrypoint]${NC} $1"; }
warn() { echo -e "${YELLOW}[entrypoint]${NC} $1"; }
err()  { echo -e "${RED}[entrypoint]${NC} $1"; exit 1; }

# ── 等待 PostgreSQL 就绪 ───────────────────────────────────
wait_for_postgres() {
    local host="${DB_HOST:-postgres}"
    local port="${DB_PORT:-5432}"
    local user="${POSTGRES_USER:-postgres}"
    local max_attempts=30
    local attempt=0

    log "等待 PostgreSQL (${host}:${port}) 就绪..."
    until pg_isready -h "$host" -p "$port" -U "$user" -q; do
        attempt=$((attempt + 1))
        if [ "$attempt" -ge "$max_attempts" ]; then
            err "PostgreSQL 在 ${max_attempts} 次尝试后仍未就绪，退出"
        fi
        warn "PostgreSQL 未就绪，等待 2 秒... (${attempt}/${max_attempts})"
        sleep 2
    done
    log "PostgreSQL 已就绪"
}

# ── 等待 Redis 就绪 ────────────────────────────────────────
wait_for_redis() {
    local host="${REDIS_HOST:-redis}"
    local port="${REDIS_PORT:-6379}"
    local max_attempts=15
    local attempt=0

    log "等待 Redis (${host}:${port}) 就绪..."
    until redis-cli -h "$host" -p "$port" ping > /dev/null 2>&1; do
        attempt=$((attempt + 1))
        if [ "$attempt" -ge "$max_attempts" ]; then
            err "Redis 在 ${max_attempts} 次尝试后仍未就绪，退出"
        fi
        warn "Redis 未就绪，等待 2 秒... (${attempt}/${max_attempts})"
        sleep 2
    done
    log "Redis 已就绪"
}

# ── 渲染配置文件 ───────────────────────────────────────────
render_config() {
    local template="/app/config/config.template.yaml"
    local output="/app/config/config.yaml"

    if [ ! -f "$template" ]; then
        err "配置模板文件不存在: ${template}"
    fi

    log "使用环境变量渲染配置文件..."
    envsubst < "$template" > "$output"
    log "配置文件已生成: ${output}"
}

# ── 主流程 ────────────────────────────────────────────────
main() {
    log "============================================"
    log " 小红书 Agent 容器启动"
    log "============================================"

    wait_for_postgres
    wait_for_redis
    render_config

    log "启动应用: $*"
    exec "$@"
}

main "$@"
