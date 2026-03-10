"""
数据采集模块

使用 Playwright 爬取已发布帖子的数据指标：
- 浏览量（views）
- 点赞数（likes）
- 收藏数（favorites）
- 评论数（comments）

每天定时执行，更新 post_records 表。
"""

import asyncio
import re
from typing import Optional, Dict, List

from playwright.async_api import async_playwright, Page
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from database.repository import PostRecordRepository
from database.models import PostRecord


class DataCollector:
    """
    小红书帖子数据采集器

    通过 Playwright 访问帖子详情页，抓取各项数据指标。
    """

    # 帖子详情页 URL 模板
    POST_URL_TEMPLATE = "https://www.xiaohongshu.com/explore/{post_id}"

    def __init__(self, db: AsyncSession):
        self.db = db
        self.post_repo = PostRecordRepository(db)

    async def _parse_count(self, text: str) -> int:
        """
        解析数量字符串（处理"1.2万"等格式）

        Args:
            text: 数量文本（如"1234"、"1.2万"、"3.5k"）

        Returns:
            整数数量
        """
        if not text:
            return 0
        text = text.strip().replace(",", "")
        try:
            if "万" in text:
                return int(float(text.replace("万", "")) * 10000)
            elif "k" in text.lower():
                return int(float(text.lower().replace("k", "")) * 1000)
            else:
                return int(re.sub(r"[^\d]", "", text) or 0)
        except (ValueError, TypeError):
            return 0

    async def collect_post_metrics(
        self,
        page: Page,
        post_id: str,
    ) -> Optional[Dict[str, int]]:
        """
        采集单篇帖子的数据指标

        Args:
            page   : Playwright Page 对象
            post_id: 小红书帖子 ID

        Returns:
            数据字典 {views, likes, favorites, comments}，失败返回 None
        """
        url = self.POST_URL_TEMPLATE.format(post_id=post_id)
        try:
            await page.goto(url, wait_until="networkidle", timeout=20000)
            await asyncio.sleep(2)  # 等待动态数据加载

            # 数据采集（选择器可能需要根据小红书实际页面调整）
            metrics = {}

            # 浏览量（通常显示在页面顶部）
            views_selectors = [
                '.views-count',
                '[class*="view"] span',
                '.note-view-count',
            ]
            views_text = await self._try_get_text(page, views_selectors)
            metrics["views"] = self._parse_count(views_text)

            # 点赞数
            likes_selectors = [
                '.like-count',
                '[class*="like"] span',
                '.note-like-count',
            ]
            likes_text = await self._try_get_text(page, likes_selectors)
            metrics["likes"] = self._parse_count(likes_text)

            # 收藏数
            favorites_selectors = [
                '.collect-count',
                '[class*="collect"] span',
                '.note-collect-count',
            ]
            favorites_text = await self._try_get_text(page, favorites_selectors)
            metrics["favorites"] = self._parse_count(favorites_text)

            # 评论数
            comments_selectors = [
                '.comment-count',
                '[class*="comment"] span',
                '.note-comment-count',
            ]
            comments_text = await self._try_get_text(page, comments_selectors)
            metrics["comments"] = self._parse_count(comments_text)

            logger.debug(
                f"帖子 {post_id} 数据: "
                f"浏览={metrics['views']}, 点赞={metrics['likes']}, "
                f"收藏={metrics['favorites']}, 评论={metrics['comments']}"
            )
            return metrics

        except Exception as e:
            logger.error(f"采集帖子 {post_id} 数据失败: {e}")
            return None

    async def _try_get_text(self, page: Page, selectors: List[str]) -> str:
        """尝试多个选择器获取文本，返回第一个成功的结果"""
        for selector in selectors:
            try:
                element = page.locator(selector).first
                text = await element.text_content(timeout=3000)
                if text and text.strip():
                    return text.strip()
            except Exception:
                continue
        return "0"

    async def collect_all_posts(self) -> int:
        """
        采集所有已发布帖子的数据

        从数据库查询有 xhs_post_id 的帖子，逐一采集数据指标。

        Returns:
            成功采集的帖子数量
        """
        # 查询所有已发布帖子（包括已有数据的，用于更新）
        posts: List[PostRecord] = await self.post_repo.get_all_published()
        valid_posts = [p for p in posts if p.xhs_post_id]

        if not valid_posts:
            logger.info("无需采集数据（没有已发布帖子）")
            return 0

        logger.info(f"开始采集 {len(valid_posts)} 篇帖子数据...")
        success_count = 0

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1366, "height": 768},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()

            for i, post in enumerate(valid_posts):
                logger.info(f"采集第 {i+1}/{len(valid_posts)} 篇: {post.title}")
                metrics = await self.collect_post_metrics(page, post.xhs_post_id)

                if metrics:
                    await self.post_repo.update_metrics(
                        record_id=post.id,
                        views=metrics["views"],
                        likes=metrics["likes"],
                        favorites=metrics["favorites"],
                        comments=metrics["comments"],
                    )
                    await self.db.commit()
                    success_count += 1
                else:
                    logger.warning(f"帖子 {post.id} 数据采集失败，跳过")

                # 访问间隔（避免频率限制）
                await asyncio.sleep(3)

            await browser.close()

        logger.info(f"数据采集完成: 成功 {success_count}/{len(valid_posts)} 篇")
        return success_count
