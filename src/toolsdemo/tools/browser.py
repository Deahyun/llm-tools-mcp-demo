"""Playwright 브라우저 세션 lifecycle.

프로세스당 **하나의 브라우저/페이지를 재사용**합니다. 도구 호출마다 새로 띄우면
로그인/조회 상태가 사라져 다단계 예매 흐름이 성립하지 않습니다.
"""

from __future__ import annotations

import asyncio
import logging

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from ..config import settings

logger = logging.getLogger(__name__)


class BrowserSession:
    """전역 단일 Playwright 세션."""

    _instance: BrowserSession | None = None
    _lock = asyncio.Lock()

    def __init__(self) -> None:
        self._pw = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    @classmethod
    async def instance(cls) -> BrowserSession:
        async with cls._lock:
            if cls._instance is None:
                cls._instance = BrowserSession()
            return cls._instance

    async def page(self) -> Page:
        if self._page is not None and not self._page.is_closed():
            return self._page
        await self._start()
        assert self._page is not None
        return self._page

    async def _start(self) -> None:
        logger.info(
            "브라우저 시작 (headless=%s, target=%s)", settings.headless, settings.target_site
        )
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=settings.headless)
        self._context = await self._browser.new_context(
            locale="ko-KR",
            timezone_id="Asia/Seoul",
            viewport={"width": 1280, "height": 900},
        )
        self._context.set_default_timeout(settings.browser_timeout_ms)
        self._page = await self._context.new_page()

    async def close(self) -> None:
        for closer in (self._context, self._browser):
            if closer is not None:
                try:
                    await closer.close()
                except Exception:  # noqa: BLE001
                    pass
        if self._pw is not None:
            try:
                await self._pw.stop()
            except Exception:  # noqa: BLE001
                pass
        self._pw = self._browser = self._context = self._page = None
        BrowserSession._instance = None
        logger.info("브라우저 종료")


async def get_page() -> Page:
    session = await BrowserSession.instance()
    return await session.page()


async def close_browser() -> None:
    if BrowserSession._instance is not None:
        await BrowserSession._instance.close()
