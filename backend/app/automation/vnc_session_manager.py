"""VNC-enabled persistent browser session manager for manual LinkedIn login."""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from app.config import get_settings
from app.security import encrypt_value

settings = get_settings()


class VNCSessionManager:
    """Manages a persistent VNC-enabled browser session for manual LinkedIn login."""

    def __init__(self):
        self._playwright: Optional[async_playwright.Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._session_id: Optional[str] = None
        self._lock = asyncio.Lock()

    async def start_session(self, session_id: str) -> dict:
        """Start a VNC-enabled browser session and return connection details."""
        async with self._lock:
            if self._browser and self._session_id == session_id:
                return {
                    "session_id": session_id,
                    "vnc_url": "vnc://localhost:5900",
                    "novnc_url": "http://localhost:6901",
                    "status": "already_running"
                }

            if self._browser:
                await self.cleanup()

            # Connect to Chrome running in VNC container via CDP
            self._playwright = await async_playwright().start()
            
            try:
                self._browser = await self._playwright.chromium.connect_over_cdp(
                    "http://vnc-browser:9222"
                )
            except Exception as e:
                # If VNC browser isn't ready, return instructions
                return {
                    "session_id": session_id,
                    "vnc_url": "vnc://34.131.105.19:5900",
                    "novnc_url": "http://34.131.105.19:6901",
                    "status": "vnc_not_ready",
                    "error": str(e),
                    "instructions": "Please ensure the VNC browser container is running and Chrome is started with remote debugging"
                }

            # Get existing contexts or create new one
            contexts = self._browser.contexts
            if contexts:
                self._context = contexts[0]
            else:
                # Create persistent context
                storage_dir = Path(settings.SESSION_STORAGE_PATH) / session_id
                storage_dir.mkdir(parents=True, exist_ok=True)
                state_path = storage_dir / "state.json"

                self._context = await self._browser.new_context(
                    viewport={"width": 1280, "height": 720},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    storage_state=str(state_path) if state_path.exists() else None,
                )

                # Add stealth scripts
                await self._context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3]});
                    Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                    window.chrome = {runtime: {}};
                """)

            # Get or create page
            pages = self._context.pages
            if pages:
                self._page = pages[0]
            else:
                self._page = await self._context.new_page()
                # Navigate to LinkedIn
                await self._page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")

            self._session_id = session_id

            return {
                "session_id": session_id,
                "vnc_url": "vnc://34.131.105.19:5900",
                "novnc_url": "http://34.131.105.19:6901",
                "status": "started",
                "debug_url": "http://localhost:9222"
            }

    async def get_session_cookies(self, session_id: str) -> Optional[str]:
        """Get encrypted cookies from the current session."""
        async with self._lock:
            if not self._context or self._session_id != session_id:
                return None

            try:
                state = await self._context.storage_state()
                state_json = json.dumps(state)
                return encrypt_value(state_json)
            except Exception:
                return None

    async def is_logged_in(self, session_id: str) -> bool:
        """Check if the user is logged into LinkedIn."""
        async with self._lock:
            if not self._page or self._session_id != session_id:
                return False

            try:
                # Check if we're no longer on login page
                current_url = self._page.url
                if "/login" not in current_url and "linkedin.com" in current_url:
                    return True
                return False
            except Exception:
                return False

    async def get_linkedin_email(self, session_id: str) -> Optional[str]:
        """Extract LinkedIn email from the current session."""
        async with self._lock:
            if not self._page or self._session_id != session_id:
                return None

            try:
                # Navigate to profile settings to get email
                await self._page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
                
                # Try to get email from profile menu
                try:
                    # Click on profile dropdown
                    await self._page.click('[data-test-id="nav-profile-sign-out-menu"]', timeout=5000)
                    await self._page.wait_for_timeout(1000)
                    
                    # Look for email in the dropdown
                    email_element = await self._page.query_selector('.pv-text-details__left-panel .text-body-small')
                    if email_element:
                        email_text = await email_element.text_content()
                        if "@" in email_text:
                            return email_text.strip()
                except Exception:
                    pass
                
                # Fallback: try to get from cookies
                state = await self._context.storage_state()
                for cookie in state.get("cookies", []):
                    if cookie.get("name") == "li_at":
                        # li_at cookie doesn't contain email, but we can try to parse from other cookies
                        pass
                
                return None
            except Exception:
                return None

    async def save_and_cleanup(self, session_id: str) -> Optional[str]:
        """Save cookies and cleanup the session."""
        cookies = await self.get_session_cookies(session_id)
        await self.cleanup()
        return cookies

    async def cleanup(self):
        """Clean up browser resources."""
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        self._page = None
        self._session_id = None


# Singleton instance
vnc_manager = VNCSessionManager()
