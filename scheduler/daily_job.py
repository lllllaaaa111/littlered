"""
任务调度模块

使用 APScheduler 定时执行每日任务：
- 08:00  生成内容（30篇帖子的文案和图片）
- 09:00  发布内容
- 18:00  抓取帖子数据
- 23:00  分析数据 + 优化策略

任务之间通过 Redis 共享数据（生成的内容缓存）。
"""

import asyncio
import json
import os
from datetime import datetime
from typing import List, Dict, Optional

import redis
import yaml
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from database.database import AsyncSessionLocal
from generators.topic_generator import TopicGenerator
from generators.content_generator import ContentGenerator
from image.image_generator import ImageGenerator
from validation.content_validator import ContentValidator
from publisher.xiaohongshu_publisher import XiaohongshuPublisher
from analytics.data_collector import DataCollector
from analytics.performance_analyzer import PerformanceAnalyzer
from optimizer.strategy_optimizer import StrategyOptimizer
from knowledge.style_repository import StyleRepository
from database.repository import PostRecordRepository, StyleCategoryRepository


def _load_config() -> dict:
    config_path = os.path.join(os.path.dirname(__file__), "../config/config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# Redis 客户端（用于跨任务共享生成内容）
def _get_redis_client() -> redis.Redis:
    config = _load_config()
    rc = config["redis"]
    return redis.Redis(
        host=rc["host"],
        port=rc["port"],
        db=rc["db"],
        password=rc.get("password") or None,
        decode_responses=True,
    )


# 每天发布的目标风格（可通过配置或 API 动态指定）
DEFAULT_STYLE = "原木风"
REDIS_CONTENT_KEY = "daily_posts_content"  # Redis 中存储生成内容的 Key
REDIS_CONTENT_TTL = 3600 * 24               # 24小时 TTL


class DailyJob:
    """
    每日任务调度器

    封装所有定时任务逻辑，通过 APScheduler 驱动。
    各任务之间通过 Redis 传递数据。
    """

    def __init__(self, style_name: str = DEFAULT_STYLE):
        self.style_name = style_name
        self.config = _load_config()
        self.daily_count = self.config["scheduler"].get("daily_post_count", 30)
        self.redis_client = _get_redis_client()
        self.scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
        self._setup_jobs()

    def _setup_jobs(self) -> None:
        """注册所有定时任务"""
        sched_cfg = self.config["scheduler"]

        # 解析时间配置（格式：HH:MM）
        gen_h, gen_m = self._parse_time(sched_cfg.get("generate_time", "08:00"))
        pub_h, pub_m = self._parse_time(sched_cfg.get("publish_time", "09:00"))
        col_h, col_m = self._parse_time(sched_cfg.get("collect_time", "18:00"))
        opt_h, opt_m = self._parse_time(sched_cfg.get("optimize_time", "23:00"))

        # 注册定时任务
        self.scheduler.add_job(
            self.job_generate_content,
            CronTrigger(hour=gen_h, minute=gen_m),
            id="generate_content",
            name="08:00 生成内容",
            replace_existing=True,
        )
        self.scheduler.add_job(
            self.job_publish_posts,
            CronTrigger(hour=pub_h, minute=pub_m),
            id="publish_posts",
            name="09:00 发布帖子",
            replace_existing=True,
        )
        self.scheduler.add_job(
            self.job_collect_data,
            CronTrigger(hour=col_h, minute=col_m),
            id="collect_data",
            name="18:00 采集数据",
            replace_existing=True,
        )
        self.scheduler.add_job(
            self.job_optimize_strategy,
            CronTrigger(hour=opt_h, minute=opt_m),
            id="optimize_strategy",
            name="23:00 优化策略",
            replace_existing=True,
        )

        logger.info(
            f"定时任务已注册: 生成({gen_h:02d}:{gen_m:02d}) | "
            f"发布({pub_h:02d}:{pub_m:02d}) | "
            f"采集({col_h:02d}:{col_m:02d}) | "
            f"优化({opt_h:02d}:{opt_m:02d})"
        )

    @staticmethod
    def _parse_time(time_str: str) -> tuple[int, int]:
        """解析 HH:MM 格式时间字符串"""
        parts = time_str.split(":")
        return int(parts[0]), int(parts[1])

    # ==================== 任务 1：生成内容 ====================

    async def job_generate_content(self) -> None:
        """
        定时任务：生成 30 篇帖子内容

        流程：
        1. 从知识库检索主题
        2. 为每个主题生成文案
        3. 为每个主题生成 4 张图片
        4. 内容校验（不合规则重试）
        5. 将生成内容缓存到 Redis
        """
        logger.info(f"====== 开始生成内容任务 [{datetime.now()}] ======")
        generated_posts = []

        try:
            async with AsyncSessionLocal() as db:
                topic_gen = TopicGenerator(db)
                content_gen = ContentGenerator()
                image_gen = ImageGenerator()
                validator = ContentValidator()
                style_repo = StyleRepository(db)

                # 1. 生成主题列表
                topics = await topic_gen.get_topics_for_batch(
                    style_name=self.style_name,
                    batch_size=self.daily_count,
                )
                logger.info(f"主题生成完成: {len(topics)} 个")

                # 2. 逐主题生成内容
                for i, topic in enumerate(topics):
                    logger.info(f"处理第 {i+1}/{len(topics)} 个主题: {topic}")
                    post_data = await self._generate_single_post(
                        topic=topic,
                        content_gen=content_gen,
                        image_gen=image_gen,
                        validator=validator,
                        style_repo=style_repo,
                    )
                    if post_data:
                        generated_posts.append(post_data)

            # 3. 缓存到 Redis
            if generated_posts:
                self.redis_client.setex(
                    REDIS_CONTENT_KEY,
                    REDIS_CONTENT_TTL,
                    json.dumps(generated_posts, ensure_ascii=False),
                )
                logger.info(f"内容生成完成: {len(generated_posts)} 篇，已缓存到 Redis")
            else:
                logger.error("内容生成失败：没有成功生成任何帖子")

        except Exception as e:
            logger.error(f"生成内容任务异常: {e}", exc_info=True)

    async def _generate_single_post(
        self,
        topic: str,
        content_gen: ContentGenerator,
        image_gen: ImageGenerator,
        validator: ContentValidator,
        style_repo: "StyleRepository",
    ) -> Optional[Dict]:
        """
        生成单篇帖子的完整内容

        Args:
            topic       : 帖子主题
            content_gen : 文案生成器
            image_gen   : 图片生成器
            validator   : 内容校验器
            style_repo  : 知识库

        Returns:
            帖子数据字典，失败返回 None
        """
        max_retries = 3

        # 检索相关参考案例
        similar_examples = await style_repo.search_examples(
            style_name=self.style_name,
            query=topic,
            n_results=3,
        )
        reference_text = "\n---\n".join([
            f"标题: {e['metadata'].get('title', '')}\n"
            for e in similar_examples
        ])

        for attempt in range(max_retries):
            # 生成文案
            content = await content_gen.generate(topic=topic, reference_examples=reference_text)
            if not content:
                logger.warning(f"主题 '{topic}' 文案生成失败（第{attempt+1}次）")
                continue

            # 尝试自动修复
            fixed_title, fixed_body = validator.auto_fix(content.title, content.body)

            # 校验内容
            result = validator.validate_all(fixed_title, fixed_body, content.tags)
            if not result.is_valid:
                if attempt < max_retries - 1:
                    logger.warning(f"内容校验失败，重试: {result.issues_summary()}")
                    content = await content_gen.regenerate(
                        topic=topic,
                        issues=result.issues_summary(),
                        previous_content=content,
                    )
                    continue
                else:
                    logger.error(f"主题 '{topic}' 经 {max_retries} 次尝试仍不合规，跳过")
                    return None

            # 生成图片
            image_paths = await image_gen.generate_post_images(
                style_name=self.style_name,
                topic=topic,
            )
            if len(image_paths) < 4:
                logger.warning(f"主题 '{topic}' 图片生成不足 4 张（{len(image_paths)} 张），使用已生成的")

            return {
                "topic": topic,
                "style_name": self.style_name,
                "title": fixed_title,
                "body": fixed_body,
                "tags": content.tags,
                "image_paths": image_paths,
            }

        return None

    # ==================== 任务 2：发布帖子 ====================

    async def job_publish_posts(self) -> None:
        """
        定时任务：发布 Redis 中缓存的帖子内容

        从 Redis 读取 job_generate_content 生成的内容，
        逐篇发布并记录到数据库。
        """
        logger.info(f"====== 开始发布任务 [{datetime.now()}] ======")

        # 从 Redis 读取缓存内容
        cached = self.redis_client.get(REDIS_CONTENT_KEY)
        if not cached:
            logger.error("Redis 中无待发布内容，请先运行生成任务")
            return

        posts = json.loads(cached)
        logger.info(f"读取到 {len(posts)} 篇待发布帖子")

        publisher = XiaohongshuPublisher()
        publish_results = []

        try:
            async with AsyncSessionLocal() as db:
                post_repo = PostRecordRepository(db)
                category_repo = StyleCategoryRepository(db)

                for i, post in enumerate(posts):
                    logger.info(f"发布第 {i+1}/{len(posts)} 篇: {post['title']}")

                    # 获取风格 ID
                    category = await category_repo.get_by_name(post["style_name"])
                    style_id = category.id if category else None

                    # 发布到小红书
                    xhs_post_id = await publisher.publish_post(
                        title=post["title"],
                        body=post["body"],
                        tags=post["tags"],
                        image_paths=post["image_paths"],
                    )

                    # 记录到数据库
                    record = await post_repo.create(
                        style_id=style_id,
                        title=post["title"],
                        content=post["body"],
                        images=post["image_paths"],
                    )
                    if xhs_post_id:
                        await post_repo.update_publish_info(record.id, xhs_post_id)

                    await db.commit()
                    publish_results.append({"title": post["title"], "xhs_id": xhs_post_id})

                    # 发布间隔
                    if i < len(posts) - 1:
                        await asyncio.sleep(publisher.publish_interval)

        except Exception as e:
            logger.error(f"发布任务异常: {e}", exc_info=True)

        success = sum(1 for r in publish_results if r["xhs_id"])
        logger.info(f"发布完成: 成功 {success}/{len(posts)} 篇")

    # ==================== 任务 3：采集数据 ====================

    async def job_collect_data(self) -> None:
        """定时任务：采集帖子数据指标"""
        logger.info(f"====== 开始数据采集任务 [{datetime.now()}] ======")
        try:
            async with AsyncSessionLocal() as db:
                collector = DataCollector(db)
                count = await collector.collect_all_posts()
                logger.info(f"数据采集完成: {count} 篇")
        except Exception as e:
            logger.error(f"数据采集任务异常: {e}", exc_info=True)

    # ==================== 任务 4：优化策略 ====================

    async def job_optimize_strategy(self) -> None:
        """定时任务：分析数据并优化内容策略"""
        logger.info(f"====== 开始策略优化任务 [{datetime.now()}] ======")
        try:
            async with AsyncSessionLocal() as db:
                optimizer = StrategyOptimizer(db)
                report = await optimizer.optimize()
                logger.info(f"策略优化完成: {report}")
        except Exception as e:
            logger.error(f"策略优化任务异常: {e}", exc_info=True)

    def start(self) -> None:
        """启动调度器"""
        self.scheduler.start()
        logger.info("定时调度器已启动")

    def stop(self) -> None:
        """停止调度器"""
        self.scheduler.shutdown()
        logger.info("定时调度器已停止")
