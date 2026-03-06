"""Browser session manager – Playwright persistent contexts with pool management."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright

from app.config import get_settings
from app.automation.anti_detection import DelayEngine, FingerprintRandomizer, ShadowBanDetector
from app.automation.proxy_manager import proxy_manager
from app.security import decrypt_value, encrypt_value

settings = get_settings()


class BrowserSession:
    """Wraps a Playwright browser context for a single LinkedIn account."""

    def __init__(self, account_id: str, context: BrowserContext, page: Page, proxy_url: Optional[str] = None):
        self.account_id = account_id
        self.context = context
        self.page = page
        self.proxy_url = proxy_url
        self._active = True

    async def close(self):
        self._active = False
        try:
            await self.context.close()
        except Exception:
            pass

    @property
    def is_active(self) -> bool:
        return self._active


class BrowserManager:
    """Manages a pool of Playwright browser sessions for concurrent users."""

    def __init__(self):
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._sessions: dict[str, BrowserSession] = {}
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(settings.BROWSER_POOL_SIZE)

    async def initialize(self):
        """Start the Playwright instance and browser."""
        async with self._lock:
            if self._playwright is None:
                self._playwright = await async_playwright().start()

            if self._browser is None:
                self._browser = await self._playwright.chromium.launch(
                    headless=settings.BROWSER_HEADLESS,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--disable-dev-shm-usage",
                        "--no-sandbox",
                        "--disable-gpu",
                        "--disable-setuid-sandbox",
                    ],
                )

    async def shutdown(self):
        """Close all sessions and the browser."""
        async with self._lock:
            for session in self._sessions.values():
                await session.close()
            self._sessions.clear()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def get_session(
        self,
        account_id: str,
        encrypted_cookies: Optional[str] = None,
        fingerprint_config: Optional[dict] = None,
    ) -> BrowserSession:
        """Get or create a browser session for the given account."""
        async with self._lock:
            if account_id in self._sessions and self._sessions[account_id].is_active:
                return self._sessions[account_id]

        await self._semaphore.acquire()
        try:
            await self.initialize()

            if self._browser is None:
                raise RuntimeError("Playwright browser is not initialized")

            # Generate fingerprint
            fingerprint = FingerprintRandomizer.generate(fingerprint_config)

            # Get proxy
            proxy_config = proxy_manager.get_proxy(account_id)
            proxy_arg = {"server": proxy_config["server"]} if proxy_config else None

            # Session storage path
            storage_dir = Path(settings.SESSION_STORAGE_PATH) / account_id
            storage_dir.mkdir(parents=True, exist_ok=True)
            state_path = storage_dir / "state.json"

            # Restore cookies if available
            storage_state = None
            if encrypted_cookies:
                try:
                    cookies_json = decrypt_value(encrypted_cookies)
                    state_data = json.loads(cookies_json)
                    state_path.write_text(json.dumps(state_data))
                    storage_state = str(state_path)
                except Exception:
                    pass

            # Create context
            context = await self._browser.new_context(
                viewport=fingerprint["viewport"],
                user_agent=fingerprint["user_agent"],
                locale=fingerprint["locale"],
                timezone_id=fingerprint["timezone_id"],
                color_scheme=fingerprint["color_scheme"],
                device_scale_factor=fingerprint["device_scale_factor"],
                has_touch=fingerprint["has_touch"],
                is_mobile=fingerprint["is_mobile"],
                extra_http_headers=fingerprint.get("extra_headers", {}),
                proxy=proxy_arg,
                storage_state=storage_state,
            )

            # Stealth: override navigator.webdriver
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3]});
                Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                window.chrome = {runtime: {}};
            """)

            page = await context.new_page()

            session = BrowserSession(
                account_id=account_id,
                context=context,
                page=page,
                proxy_url=proxy_config["server"] if proxy_config else None,
            )

            async with self._lock:
                self._sessions[account_id] = session

            return session

        except Exception:
            self._semaphore.release()
            raise

    async def release_session(self, account_id: str):
        """Close and remove a session from the pool."""
        async with self._lock:
            session = self._sessions.pop(account_id, None)
        if session:
            await session.close()
            self._semaphore.release()

    async def save_session_cookies(self, account_id: str) -> Optional[str]:
        """Export and encrypt current session cookies."""
        async with self._lock:
            session = self._sessions.get(account_id)
        if not session or not session.is_active:
            return None

        try:
            state = await session.context.storage_state()
            state_json = json.dumps(state)
            encrypted = encrypt_value(state_json)
            return encrypted
        except Exception:
            return None

    async def check_session_valid(self, account_id: str) -> bool:
        """Check if the LinkedIn session is still authenticated."""
        async with self._lock:
            session = self._sessions.get(account_id)
        if not session or not session.is_active:
            return False

        try:
            await session.page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30000)
            await DelayEngine.delay("page_load")

            # Check if redirected to login
            url = session.page.url
            if "/login" in url or "/authwall" in url or "/checkpoint" in url:
                return False

            # Check for shadow-ban signals
            signals = await ShadowBanDetector.check_signals(session.page)
            if signals["restricted"]:
                return False

            return True
        except Exception:
            return False

    @property
    def active_sessions(self) -> int:
        return len(self._sessions)

    @property
    def pool_capacity(self) -> int:
        return settings.BROWSER_POOL_SIZE


# Singleton
browser_manager = BrowserManager()
