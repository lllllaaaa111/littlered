from __future__ import annotations

from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.database.models import ImageAsset, Post, PublishEvent


class XiaohongshuPublisher:
    """
    Best-effort Playwright automation.

    Xiaohongshu frequently changes UI; you may need to tweak selectors in:
    - _goto_create()
    - _fill_content()
    - _upload_images()
    - _submit()
    """

    def publish(self, *, post_id: int, session: Session) -> dict[str, Any]:
        post = session.get(Post, post_id)
        if post is None:
            raise ValueError(f"post {post_id} not found")
        img = session.scalar(select(ImageAsset).where(ImageAsset.post_id == post_id))
        if img is None:
            raise ValueError(f"post {post_id} has no image")
        image_path = Path(img.file_path)
        if not image_path.exists():
            raise FileNotFoundError(str(image_path))

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=settings.xhs_headless)
            ctx = browser.new_context(storage_state=str(settings.storage_state_path()))
            page = ctx.new_page()

            page.goto(settings.xhs_base_url, wait_until="domcontentloaded")

            self._goto_create(page)
            self._upload_images(page, [image_path])
            self._fill_content(page, title=post.title, body=post.body, hashtags=post.hashtags)
            self._submit(page)

            # Try to capture resulting URL / id
            page.wait_for_timeout(2000)
            external_url = page.url

            ctx.close()
            browser.close()

        # Try to infer external_post_id from latest publish event url (fallback to url)
        external_post_id = None
        return {"external_post_id": external_post_id, "external_url": external_url}

    def _goto_create(self, page) -> None:
        # Common entry: “发布/创作/发布笔记” buttons.
        page.wait_for_timeout(1500)
        for sel in [
            "text=发布",
            "text=发布笔记",
            "text=创作",
            "[data-testid='publish']",
        ]:
            try:
                page.locator(sel).first.click(timeout=1500)
                return
            except Exception:
                continue
        # Fallback: navigate to creator center (may change)
        page.goto(f"{settings.xhs_base_url}/publish", wait_until="domcontentloaded")

    def _upload_images(self, page, image_paths: list[Path]) -> None:
        page.wait_for_timeout(1000)
        upload = None
        for sel in [
            "input[type='file']",
            "input[type='file'][accept*='image']",
        ]:
            loc = page.locator(sel)
            if loc.count() > 0:
                upload = loc.first
                break
        if upload is None:
            raise RuntimeError("Could not find image upload input. Update selectors in _upload_images().")

        upload.set_input_files([str(p) for p in image_paths])
        page.wait_for_timeout(2000)

    def _fill_content(self, page, *, title: str, body: str, hashtags: list[str]) -> None:
        page.wait_for_timeout(1000)

        # Title
        for sel in [
            "textarea[placeholder*='标题']",
            "input[placeholder*='标题']",
            "text=标题 >> .. >> textarea",
        ]:
            try:
                page.locator(sel).first.fill(title, timeout=1500)
                break
            except Exception:
                continue

        # Body / content
        content = body
        if hashtags:
            content = content + "\n\n" + " ".join(hashtags)
        filled = False
        for sel in [
            "textarea[placeholder*='正文']",
            "textarea[placeholder*='内容']",
            "div[contenteditable='true']",
        ]:
            try:
                loc = page.locator(sel).first
                loc.click(timeout=1500)
                loc.fill(content, timeout=1500)
                filled = True
                break
            except Exception:
                continue
        if not filled:
            raise RuntimeError("Could not fill post content. Update selectors in _fill_content().")

    def _submit(self, page) -> None:
        page.wait_for_timeout(1000)
        for sel in [
            "text=发布",
            "button:has-text('发布')",
            "text=立即发布",
        ]:
            try:
                page.locator(sel).first.click(timeout=1500)
                page.wait_for_timeout(2000)
                return
            except Exception:
                continue
        raise RuntimeError("Could not submit publish. Update selectors in _submit().")

