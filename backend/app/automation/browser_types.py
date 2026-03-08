"""Shared browser session types – no heavy imports to prevent circular dependencies."""

from __future__ import annotations

from typing import Optional

from playwright.async_api import BrowserContext, Page


class BrowserSession:
    """Wraps a Playwright browser context for a single LinkedIn account."""

    def __init__(
        self,
        account_id: str,
        context: BrowserContext,
        page: Page,
        proxy_url: Optional[str] = None,
    ) -> None:
        self.account_id = account_id
        self.context = context
        self.page = page
        self.proxy_url = proxy_url
        self._active = True

    async def close(self) -> None:
        self._active = False
        try:
            await self.context.close()
        except Exception:
            pass

    @property
    def is_active(self) -> bool:
        return self._active
