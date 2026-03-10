"""
小红书自动发布模块

使用 Playwright 模拟浏览器操作，自动完成：
1. 登录小红书创作者中心
2. 上传图片（4 张）
3. 输入标题
4. 输入正文（包含标签）
5. 发布帖子并获取帖子 ID

重要：请确保已安装 Playwright 浏览器驱动
  $ playwright install chromium
"""

import os
import json
import asyncio
from pathlib import Path
from typing import List, Optional

import yaml
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from loguru import logger


def _load_config() -> dict:
    config_path = os.path.join(os.path.dirname(__file__), "../config/config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class XiaohongshuPublisher:
    """
    小红书自动发布器

    使用 Playwright 自动化浏览器完成帖子发布流程。
    支持 Cookie 登录（推荐）和账号密码登录两种方式。
    """

    # 小红书创作者平台 URL
    CREATOR_URL = "https://creator.xiaohongshu.com"
    UPLOAD_URL = "https://creator.xiaohongshu.com/publish/publish"
    LOGIN_URL = "https://www.xiaohongshu.com/login"

    def __init__(self):
        config = _load_config()
        xhs_cfg = config["xiaohongshu"]

        self.username = xhs_cfg.get("username", "")
        self.password = xhs_cfg.get("password", "")
        self.cookie_file = xhs_cfg.get("cookie_file", "./cookies/xhs_cookies.json")
        self.publish_interval = xhs_cfg.get("publish_interval", 120)  # 发布间隔（秒）

        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    async def _setup_browser(self) -> BrowserContext:
        """
        初始化浏览器和上下文

        优先使用 Cookie 登录，减少验证码风险。
        """
        playwright = await async_playwright().start()
        self._browser = await playwright.chromium.launch(
            headless=False,  # 建议调试时设为 False，生产环境可改 True
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        )

        # 创建浏览器上下文（模拟真实用户环境）
        self._context = await self._browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )

        # 尝试加载已保存的 Cookies
        if os.path.exists(self.cookie_file):
            with open(self.cookie_file, "r", encoding="utf-8") as f:
                cookies = json.load(f)
            await self._context.add_cookies(cookies)
            logger.info("已加载保存的 Cookies")

        return self._context

    async def _save_cookies(self, page: Page) -> None:
        """保存当前会话 Cookies 到文件"""
        cookies = await self._context.cookies()
        cookie_dir = Path(self.cookie_file).parent
        cookie_dir.mkdir(parents=True, exist_ok=True)
        with open(self.cookie_file, "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
        logger.info("Cookies 已保存")

    async def _login(self, page: Page) -> bool:
        """
        登录小红书

        流程：
        1. 先尝试直接访问创作者中心（Cookie 登录）
        2. 如果跳转到登录页，则进行账号密码登录
        """
        await page.goto(self.CREATOR_URL, wait_until="networkidle")

        # 检查是否已登录（是否跳转到登录页）
        if "login" in page.url or "xiaohongshu.com/login" in page.url:
            logger.info("检测到未登录状态，开始登录...")

            if not self.username or not self.password:
                logger.error("未配置账号密码，且无有效 Cookie，请手动登录后保存 Cookie")
                # 等待用户手动登录（最多等 60 秒）
                logger.info("等待手动登录（60秒）...")
                await page.wait_for_url(
                    f"{self.CREATOR_URL}/**",
                    timeout=60000,
                )
            else:
                # 账号密码登录
                await page.goto(self.LOGIN_URL)
                await page.wait_for_load_state("networkidle")

                # 输入账号
                await page.fill('input[placeholder*="手机号"]', self.username)
                await asyncio.sleep(0.5)

                # 输入密码
                await page.fill('input[type="password"]', self.password)
                await asyncio.sleep(0.5)

                # 点击登录按钮
                await page.click('button[type="submit"]')
                await page.wait_for_url(f"{self.CREATOR_URL}/**", timeout=30000)

            # 保存 Cookies
            await self._save_cookies(page)

        logger.info("登录成功")
        return True

    async def publish_post(
        self,
        title: str,
        body: str,
        tags: List[str],
        image_paths: List[str],
    ) -> Optional[str]:
        """
        发布一篇小红书帖子

        Args:
            title      : 帖子标题（≤20字）
            body       : 帖子正文（≤500字）
            tags       : 话题标签列表
            image_paths: 本地图片路径列表（4张）

        Returns:
            成功返回小红书帖子 ID，失败返回 None
        """
        context = await self._setup_browser()
        page = await context.new_page()

        try:
            # 步骤 1：登录
            await self._login(page)

            # 步骤 2：进入发布页面
            await page.goto(self.UPLOAD_URL, wait_until="networkidle")
            await asyncio.sleep(2)

            # 步骤 3：上传图片
            logger.info(f"开始上传 {len(image_paths)} 张图片")
            await self._upload_images(page, image_paths)
            await asyncio.sleep(3)

            # 步骤 4：输入标题
            logger.info(f"输入标题: {title}")
            await self._fill_title(page, title)
            await asyncio.sleep(1)

            # 步骤 5：输入正文和标签
            logger.info("输入正文和标签")
            full_body = body + "\n" + "".join([f"#{tag}" for tag in tags])
            await self._fill_body(page, full_body)
            await asyncio.sleep(1)

            # 步骤 6：点击发布
            logger.info("点击发布按钮")
            post_id = await self._click_publish(page)

            if post_id:
                logger.info(f"帖子发布成功，ID: {post_id}")
            else:
                logger.warning("帖子可能已发布，但未获取到 ID")

            return post_id

        except Exception as e:
            logger.error(f"发布失败: {e}")
            # 截图留存
            await page.screenshot(path=f"./storage/temp/error_{title[:10]}.png")
            return None

        finally:
            await page.close()
            await context.close()
            if self._browser:
                await self._browser.close()

    async def _upload_images(self, page: Page, image_paths: List[str]) -> None:
        """上传图片到小红书"""
        # 等待上传按钮出现
        upload_input = page.locator('input[type="file"]').first
        await upload_input.wait_for(state="attached", timeout=10000)

        # 上传所有图片
        await upload_input.set_input_files(image_paths)

        # 等待图片上传完成（检查缩略图是否出现）
        await page.wait_for_selector(
            '.upload-item',
            state="visible",
            timeout=30000,
        )
        logger.debug(f"图片上传完成: {len(image_paths)} 张")

    async def _fill_title(self, page: Page, title: str) -> None:
        """填写帖子标题"""
        # 小红书标题输入框选择器（可能需要根据实际页面调整）
        title_selectors = [
            'input[placeholder*="标题"]',
            '.title-input input',
            '#post-title',
        ]
        for selector in title_selectors:
            try:
                await page.fill(selector, title, timeout=5000)
                return
            except Exception:
                continue
        logger.warning("未找到标题输入框，尝试使用键盘输入")

    async def _fill_body(self, page: Page, body: str) -> None:
        """填写帖子正文"""
        # 富文本编辑器选择器
        body_selectors = [
            '.ql-editor',
            '[contenteditable="true"]',
            '.content-input',
        ]
        for selector in body_selectors:
            try:
                element = page.locator(selector).first
                await element.click(timeout=5000)
                await element.fill(body)
                return
            except Exception:
                continue
        logger.warning("未找到正文输入框")

    async def _click_publish(self, page: Page) -> Optional[str]:
        """点击发布按钮并获取帖子 ID"""
        publish_selectors = [
            'button:has-text("发布")',
            '.publish-btn',
            '[class*="publish"]',
        ]
        for selector in publish_selectors:
            try:
                await page.click(selector, timeout=5000)
                break
            except Exception:
                continue

        # 等待发布成功（URL 变化或成功提示）
        try:
            await page.wait_for_url("**/success**", timeout=15000)
            # 从 URL 中提取帖子 ID
            current_url = page.url
            post_id = current_url.split("/")[-1].split("?")[0]
            return post_id if post_id else None
        except Exception:
            # 无法从 URL 获取 ID，尝试从成功提示中获取
            try:
                await page.wait_for_selector('.success-tip', timeout=10000)
                return "published_" + str(int(asyncio.get_event_loop().time()))
            except Exception:
                return None

    async def batch_publish(
        self,
        posts: List[dict],
        interval: int = None,
    ) -> List[Optional[str]]:
        """
        批量发布帖子

        Args:
            posts   : 帖子数据列表，每条包含 title/body/tags/image_paths
            interval: 发布间隔（秒），默认使用配置值

        Returns:
            每篇帖子的 ID 列表（失败为 None）
        """
        interval = interval or self.publish_interval
        post_ids = []

        for i, post in enumerate(posts):
            logger.info(f"发布第 {i+1}/{len(posts)} 篇: {post['title']}")
            post_id = await self.publish_post(
                title=post["title"],
                body=post["body"],
                tags=post.get("tags", []),
                image_paths=post["image_paths"],
            )
            post_ids.append(post_id)

            # 发布间隔（避免触发频率限制）
            if i < len(posts) - 1:
                logger.info(f"等待 {interval} 秒后发布下一篇...")
                await asyncio.sleep(interval)

        logger.info(f"批量发布完成: 成功 {sum(1 for p in post_ids if p)} / {len(posts)} 篇")
        return post_ids
