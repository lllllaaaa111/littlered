from __future__ import annotations

from playwright.sync_api import sync_playwright

from app.config.settings import settings


def main() -> None:
    """
    Opens a browser to let you login manually, then saves Playwright storage state.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(settings.xhs_base_url, wait_until="domcontentloaded")
        print("Login in the opened browser, then return here and press Enter to save storage state.")
        input()
        ctx.storage_state(path=str(settings.storage_state_path()))
        ctx.close()
        browser.close()


if __name__ == "__main__":
    main()

