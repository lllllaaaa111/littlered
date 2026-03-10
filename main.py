"""
小红书自动运营 Agent 主入口

提供两种运行模式：
1. FastAPI HTTP API 模式（生产环境）
2. CLI 命令行模式（调试/手动触发）

API 路由：
  POST /api/run-agent      手动触发 Agent 完整流程
  POST /api/generate       生成指定风格内容
  POST /api/publish        发布待发布内容
  GET  /api/status         查看系统状态
  GET  /api/report         获取数据分析报告
  POST /api/optimize       手动触发策略优化

启动命令：
  uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

import asyncio
import sys
import os
from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from database.database import init_db, close_db, get_db
from knowledge.style_repository import StyleRepository
from generators.topic_generator import TopicGenerator
from generators.content_generator import ContentGenerator
from image.image_generator import ImageGenerator
from validation.content_validator import ContentValidator
from analytics.data_collector import DataCollector
from analytics.performance_analyzer import PerformanceAnalyzer
from optimizer.strategy_optimizer import StrategyOptimizer
from scheduler.daily_job import DailyJob

# ===== 日志配置 =====
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO",
)
logger.add(
    "./logs/agent.log",
    rotation="1 day",
    retention="30 days",
    encoding="utf-8",
    level="DEBUG",
)

# 全局调度器实例
_daily_job: Optional[DailyJob] = None


# ===== 应用生命周期 =====

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI 应用启动/关闭生命周期管理"""
    global _daily_job

    # ---- 启动阶段 ----
    logger.info("小红书 Agent 系统启动中...")

    # 创建必要目录
    os.makedirs("./logs", exist_ok=True)
    os.makedirs("./storage/images", exist_ok=True)
    os.makedirs("./storage/temp", exist_ok=True)
    os.makedirs("./cookies", exist_ok=True)

    # 初始化数据库
    await init_db()

    # 初始化种子数据
    async with __import__("database.database", fromlist=["AsyncSessionLocal"]).AsyncSessionLocal() as db:
        style_repo = StyleRepository(db)
        await style_repo.initialize_seed_data()

    # 启动定时调度器
    _daily_job = DailyJob()
    _daily_job.start()

    logger.info("系统启动完成，等待定时任务触发")
    yield

    # ---- 关闭阶段 ----
    if _daily_job:
        _daily_job.stop()
    await close_db()
    logger.info("系统已安全关闭")


# ===== FastAPI 应用实例 =====

app = FastAPI(
    title="小红书自动运营 Agent",
    description="自动生成并发布小红书装修类内容，每天发布 30 篇原创帖子",
    version="1.0.0",
    lifespan=lifespan,
)


# ===== 请求/响应数据模型 =====

class AgentRunRequest(BaseModel):
    style_name: str = "原木风"
    post_count: int = 30


class GenerateRequest(BaseModel):
    style_name: str = "原木风"
    post_count: int = 5


class StyleOptimizeRequest(BaseModel):
    style_name: Optional[str] = None  # None 表示优化所有风格


# ===== API 路由 =====

@app.get("/", summary="系统健康检查")
async def root():
    return {"status": "running", "system": "小红书自动运营 Agent", "version": "1.0.0"}


@app.get("/api/status", summary="查看系统状态")
async def get_status(db: AsyncSession = Depends(get_db)):
    """返回数据库统计、调度器状态等信息"""
    from database.repository import PostRecordRepository, StyleCategoryRepository
    post_repo = PostRecordRepository(db)
    cat_repo = StyleCategoryRepository(db)

    all_posts = await post_repo.get_all_published()
    categories = await cat_repo.get_all()

    return {
        "scheduler_running": _daily_job.scheduler.running if _daily_job else False,
        "total_published": len(all_posts),
        "total_styles": len(categories),
        "styles": [c.style_name for c in categories],
    }


@app.post("/api/run-agent", summary="手动触发完整 Agent 流程")
async def run_agent(
    request: AgentRunRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    手动触发完整流程：
    风格检索 → 主题生成 → 文案生成 → 图片生成 → 校验 → 发布
    """
    background_tasks.add_task(
        _run_full_pipeline,
        style_name=request.style_name,
        post_count=request.post_count,
    )
    return {"status": "started", "message": f"Agent 已在后台启动，风格: {request.style_name}，数量: {request.post_count}"}


@app.post("/api/generate", summary="仅生成内容（不发布）")
async def generate_content(
    request: GenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    """生成内容并缓存到 Redis，不执行发布"""
    if _daily_job is None:
        raise HTTPException(status_code=503, detail="调度器未启动")

    await _daily_job.job_generate_content()
    return {"status": "completed", "message": f"已生成 {request.post_count} 篇内容并缓存"}


@app.post("/api/publish", summary="发布已生成的内容")
async def publish_posts(background_tasks: BackgroundTasks):
    """读取 Redis 缓存内容并发布"""
    if _daily_job is None:
        raise HTTPException(status_code=503, detail="调度器未启动")

    background_tasks.add_task(_daily_job.job_publish_posts)
    return {"status": "started", "message": "发布任务已在后台启动"}


@app.get("/api/report", summary="获取数据分析报告")
async def get_report(db: AsyncSession = Depends(get_db)):
    """返回帖子表现分析报告"""
    analyzer = PerformanceAnalyzer(db)
    report = await analyzer.analyze_all_posts()
    return report


@app.post("/api/optimize", summary="手动触发策略优化")
async def optimize_strategy(
    request: StyleOptimizeRequest,
    db: AsyncSession = Depends(get_db),
):
    """分析帖子数据，调整主题权重"""
    optimizer = StrategyOptimizer(db)
    result = await optimizer.optimize()
    return result


@app.get("/api/topics", summary="查看风格主题列表")
async def get_topics(style_name: str = "原木风", db: AsyncSession = Depends(get_db)):
    """查看某风格下的主题关键词"""
    style_repo = StyleRepository(db)
    topics = await style_repo.get_topics_by_style(style_name, limit=20)
    return {"style": style_name, "topics": topics, "count": len(topics)}


@app.post("/api/collect-data", summary="手动触发数据采集")
async def collect_data(background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    """采集已发布帖子的数据指标"""
    background_tasks.add_task(_run_collect, db)
    return {"status": "started", "message": "数据采集任务已在后台启动"}


# ===== 后台任务函数 =====

async def _run_full_pipeline(style_name: str, post_count: int) -> None:
    """完整 Agent 流程（后台执行）"""
    logger.info(f"完整流程启动: 风格={style_name}, 数量={post_count}")
    job = DailyJob(style_name=style_name)
    job.daily_count = post_count
    await job.job_generate_content()
    await job.job_publish_posts()
    logger.info("完整流程执行完毕")


async def _run_collect(db: AsyncSession) -> None:
    """数据采集后台任务"""
    collector = DataCollector(db)
    await collector.collect_all_posts()


# ===== CLI 入口 =====

async def cli_main():
    """命令行模式：执行单次完整流程（用于调试）"""
    from database.database import AsyncSessionLocal

    logger.info("CLI 模式启动")

    # 初始化数据库
    await init_db()

    # 初始化种子数据
    async with AsyncSessionLocal() as db:
        style_repo = StyleRepository(db)
        await style_repo.initialize_seed_data()

    # 执行生成 + 发布流程
    job = DailyJob(style_name="原木风")
    job.daily_count = 5  # CLI 模式测试 5 篇

    logger.info("步骤 1：生成内容")
    await job.job_generate_content()

    logger.info("步骤 2：发布内容")
    await job.job_publish_posts()

    await close_db()
    logger.info("CLI 流程完成")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "cli":
        # CLI 模式
        asyncio.run(cli_main())
    else:
        # FastAPI 模式
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=8000,
            reload=True,
            log_level="info",
        )
