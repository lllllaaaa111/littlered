from __future__ import annotations

from typing import Any

from playwright.sync_api import sync_playwright
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.database.models import Comment, MetricSnapshot, Post, PublishEvent


class MetricsCollector:
    """
    Metrics/comments collection via Playwright scraping (best-effort).

    If you have an internal API or a stable endpoint, replace these methods.
    """

    def _latest_publish(self, *, post_id: int, session: Session) -> PublishEvent | None:
        return session.scalar(
            select(PublishEvent)
            .where(PublishEvent.post_id == post_id)
            .order_by(desc(PublishEvent.created_at))
            .limit(1)
        )

    def collect(self, *, post_id: int, session: Session) -> dict[str, Any]:
        ev = self._latest_publish(post_id=post_id, session=session)
        if ev is None or not ev.success:
            raise RuntimeError(f"post {post_id} not published yet")
        url = ev.external_url
        if not url:
            # As a fallback, do nothing.
            return {"external_post_id": ev.external_post_id, "views": 0, "likes": 0, "collects": 0, "comments": 0, "shares": 0}

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=settings.xhs_headless)
            ctx = browser.new_context(storage_state=str(settings.storage_state_path()))
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)

            # Try to parse numbers from common labels (likes/收藏/评论)
            text = page.inner_text("body")
            ctx.close()
            browser.close()

        def _extract(label: str) -> int:
            # very light heuristic; UI may change
            import re

            m = re.search(rf"{label}\\s*([0-9]+)", text)
            return int(m.group(1)) if m else 0

        likes = _extract("赞") or _extract("点赞")
        collects = _extract("收藏")
        comments = _extract("评论")
        shares = _extract("分享")
        views = _extract("浏览") or _extract("阅读")

        return {
            "external_post_id": ev.external_post_id,
            "views": views,
            "likes": likes,
            "collects": collects,
            "comments": comments,
            "shares": shares,
        }

    def fetch_comments(self, *, post_id: int, session: Session) -> list[dict[str, Any]]:
        ev = self._latest_publish(post_id=post_id, session=session)
        if ev is None or not ev.success or not ev.external_url:
            return []

        url = ev.external_url
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=settings.xhs_headless)
            ctx = browser.new_context(storage_state=str(settings.storage_state_path()))
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)

            # Attempt to open comments panel
            for sel in ["text=评论", "button:has-text('评论')", "[data-testid='comment']"]:
                try:
                    page.locator(sel).first.click(timeout=1000)
                    break
                except Exception:
                    continue
            page.wait_for_timeout(1500)

            # Collect visible comment blocks
            comments: list[dict[str, Any]] = []
            blocks = page.locator("[class*='comment'], [data-testid*='comment']")
            n = min(blocks.count(), 30)
            for i in range(n):
                b = blocks.nth(i)
                content = ""
                author = None
                try:
                    content = b.inner_text(timeout=500).strip()
                except Exception:
                    continue
                if not content:
                    continue
                comments.append(
                    {
                        "external_comment_id": f"visible_{i}",
                        "author": author,
                        "content": content[:2000],
                    }
                )

            ctx.close()
            browser.close()

        return comments

