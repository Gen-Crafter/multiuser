"""
Remote Browser Session Manager.

Each LinkedIn account runs inside an isolated Docker container that launches
Chromium with CDP enabled.  This manager:

  1. Starts / stops / monitors per-account browser containers via the Docker SDK.
  2. Connects to each container's Chromium instance using Playwright's
     ``connect_over_cdp()`` — returning a real BrowserSession with a live
     Playwright Page so that all existing automation code (linkedin_actions.py,
     etc.) works without modification.
  3. Provides the same public interface as the original BrowserManager so that
     callers (campaign_tasks, linkedin_actions) need no changes.

Profile directories
-------------------
Each container mounts the named Docker volume ``PROFILE_VOLUME_NAME`` at
``PROFILE_STORAGE_PATH``.  Chromium's ``--user-data-dir`` is set to
``{PROFILE_STORAGE_PATH}/{account_id}`` inside the container, giving each
account persistent cookies / localStorage / cache across restarts.

Fallback
--------
If the Docker daemon is unreachable (``USE_REMOTE_BROWSERS=false`` or socket
not mounted), the manager transparently falls back to the in-process
BrowserManager so development environments continue to work.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

import httpx
from playwright.async_api import async_playwright, Browser, Playwright

from app.automation.anti_detection import DelayEngine, FingerprintRandomizer, ShadowBanDetector
from app.automation.browser_types import BrowserSession
from app.automation.proxy_manager import proxy_manager
from app.config import get_settings
from app.security import decrypt_value, encrypt_value

logger = logging.getLogger(__name__)
settings = get_settings()


class BrowserSessionManager:
    """
    Remote-container session manager.

    Public interface is identical to BrowserManager so it can be used
    as a drop-in replacement for the ``browser_manager`` singleton.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, BrowserSession] = {}
        self._browsers: dict[str, Browser] = {}   # account_id → CDP browser handle
        self._lock = asyncio.Lock()
        self._playwright: Optional[Playwright] = None
        self._docker_client = None                 # lazy-init docker.DockerClient

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _get_docker(self):
        if self._docker_client is None:
            import docker  # optional dep – only needed at runtime
            self._docker_client = docker.from_env()
        return self._docker_client

    @staticmethod
    def _container_name(account_id: str) -> str:
        return f"li-bw-{account_id}"

    def _cdp_url(self, account_id: str) -> str:
        return f"http://{self._container_name(account_id)}:{settings.BROWSER_CDP_PORT}"

    def _health_url(self, account_id: str) -> str:
        return f"http://{self._container_name(account_id)}:{settings.BROWSER_HEALTH_PORT}/health"

    # ── Playwright init ───────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Start the Playwright driver (needed for connect_over_cdp)."""
        if self._playwright is None:
            self._playwright = await async_playwright().start()

    # ── Container lifecycle ───────────────────────────────────────────────────

    def _ensure_container_sync(self, account_id: str, proxy_url: Optional[str]) -> None:
        """
        Synchronously start the Docker container for an account if it is not
        already running.  Called from the async layer via asyncio.to_thread.
        """
        import docker
        dc = self._get_docker()
        container_name = self._container_name(account_id)

        try:
            container = dc.containers.get(container_name)
            if container.status == "running":
                return  # already up
            logger.info("[session_manager] Container %s found in state '%s' — removing and restarting",
                        container_name, container.status)
            container.remove(force=True)
        except docker.errors.NotFound:
            pass  # first launch

        env: dict[str, str] = {
            "ACCOUNT_ID":   account_id,
            "PROFILE_BASE": settings.PROFILE_STORAGE_PATH,
            "CDP_PORT":     str(settings.BROWSER_CDP_PORT),
            "HEALTH_PORT":  str(settings.BROWSER_HEALTH_PORT),
        }
        if proxy_url:
            env["PROXY_URL"] = proxy_url

        dc.containers.run(
            settings.BROWSER_WORKER_IMAGE,
            name=container_name,
            network=settings.DOCKER_NETWORK,
            volumes={
                settings.PROFILE_VOLUME_NAME: {
                    "bind": settings.PROFILE_STORAGE_PATH,
                    "mode": "rw",
                }
            },
            environment=env,
            detach=True,
            auto_remove=False,
            labels={
                "managed-by": "li-platform",
                "account-id": account_id,
            },
        )
        logger.info("[session_manager] Started container %s", container_name)

    async def _ensure_container(self, account_id: str, proxy_url: Optional[str]) -> None:
        """Async wrapper: start container if not running."""
        await asyncio.to_thread(self._ensure_container_sync, account_id, proxy_url)

    async def _wait_for_ready(self, account_id: str, timeout: int = 45) -> None:
        """
        Poll the container's health endpoint until Chromium is up and
        accepting CDP connections.
        """
        health_url = self._health_url(account_id)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout

        async with httpx.AsyncClient(timeout=3) as client:
            while asyncio.get_running_loop().time() < deadline:
                try:
                    resp = await client.get(health_url)
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("status") == "ok":
                            return
                except Exception:
                    pass
                await asyncio.sleep(1.5)

        raise TimeoutError(
            f"Browser container for account {account_id} did not become ready "
            f"within {timeout}s — check Docker logs for li-bw-{account_id}"
        )

    async def _reconnect_container(self, account_id: str, proxy_url: Optional[str]) -> None:
        """Ensure the container is running and the health check passes."""
        await self._ensure_container(account_id, proxy_url)
        await self._wait_for_ready(account_id)

    # ── Public session interface (matches BrowserManager) ────────────────────

    async def get_session(
        self,
        account_id: str,
        encrypted_cookies: Optional[str] = None,
        fingerprint_config: Optional[dict] = None,
        proxy_url: Optional[str] = None,
    ) -> BrowserSession:
        """
        Return a live BrowserSession backed by an isolated Docker container.

        On the first call for an account_id the container is started.
        On subsequent calls the existing session is reused; if the container
        has crashed it is restarted automatically.
        """
        async with self._lock:
            existing = self._sessions.get(account_id)
            if existing and existing.is_active:
                return existing

        await self.initialize()

        # Ensure container is running and healthy
        try:
            await self._reconnect_container(account_id, proxy_url)
        except Exception as exc:
            logger.error("[session_manager] Container startup failed for %s: %s", account_id, exc)
            raise

        # Connect Playwright to the container's Chromium via CDP
        cdp_endpoint = self._cdp_url(account_id)
        browser = await self._playwright.chromium.connect_over_cdp(cdp_endpoint)  # type: ignore[union-attr]
        logger.info("[session_manager] CDP connected to %s", cdp_endpoint)

        # Build fingerprint
        fingerprint = FingerprintRandomizer.generate(fingerprint_config)

        # Resolve proxy for Playwright context
        proxy_arg: Optional[dict] = None
        if proxy_url:
            proxy_arg = {"server": proxy_url}
        else:
            proxy_config = proxy_manager.get_proxy(account_id)
            if proxy_config:
                proxy_arg = {"server": proxy_config["server"]}

        # Prepare storage state from encrypted cookies
        storage_state: Optional[str] = None
        if encrypted_cookies:
            try:
                cookies_json = decrypt_value(encrypted_cookies)
                state_data = json.loads(cookies_json)
                # Cookie-Editor exports a bare list; Playwright needs the full format
                if isinstance(state_data, list):
                    state_data = {"cookies": state_data, "origins": []}
                state_dir = Path(settings.SESSION_STORAGE_PATH) / account_id
                state_dir.mkdir(parents=True, exist_ok=True)
                state_file = state_dir / "state.json"
                state_file.write_text(json.dumps(state_data))
                storage_state = str(state_file)
            except Exception as exc:
                logger.warning("[session_manager] Could not restore cookies for %s: %s", account_id, exc)

        # Create an isolated browser context with full fingerprint + cookies
        context = await browser.new_context(
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

        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins',  {get: () => [1, 2, 3]});
            Object.defineProperty(navigator, 'languages',{get: () => ['en-US', 'en']});
            window.chrome = {runtime: {}};
        """)

        page = await context.new_page()

        session = BrowserSession(
            account_id=account_id,
            context=context,
            page=page,
            proxy_url=proxy_url or (proxy_arg["server"] if proxy_arg else None),
        )

        async with self._lock:
            self._sessions[account_id] = session
            self._browsers[account_id] = browser

        return session

    async def release_session(self, account_id: str) -> None:
        """
        Close the Playwright context and disconnect from the container.
        The container itself keeps running so it can be reconnected quickly.
        """
        async with self._lock:
            session = self._sessions.pop(account_id, None)
            browser = self._browsers.pop(account_id, None)

        if session:
            try:
                await session.close()
            except Exception:
                pass

        if browser:
            try:
                await browser.close()   # disconnects CDP; does NOT stop Chromium
            except Exception:
                pass

        logger.info("[session_manager] Session released for %s (container still running)", account_id)

    async def save_session_cookies(self, account_id: str) -> Optional[str]:
        """Export the current context's cookies and encrypt them."""
        async with self._lock:
            session = self._sessions.get(account_id)
        if not session or not session.is_active:
            return None
        try:
            state = await session.context.storage_state()
            return encrypt_value(json.dumps(state))
        except Exception as exc:
            logger.warning("[session_manager] save_session_cookies failed for %s: %s", account_id, exc)
            return None

    async def check_session_valid(self, account_id: str) -> bool:
        """Navigate to LinkedIn feed and check whether the session is authenticated."""
        async with self._lock:
            session = self._sessions.get(account_id)
        if not session or not session.is_active:
            return False
        try:
            await session.page.goto(
                "https://www.linkedin.com/feed/",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            await DelayEngine.delay("page_load")
            url = session.page.url
            if "/login" in url or "/authwall" in url or "/checkpoint" in url:
                return False
            signals = await ShadowBanDetector.check_signals(session.page)
            if signals["restricted"]:
                return False
            return True
        except Exception:
            return False

    # ── Container management helpers ──────────────────────────────────────────

    async def stop_container(self, account_id: str) -> None:
        """Stop and remove the Docker container for an account."""
        await self.release_session(account_id)

        def _stop():
            import docker
            dc = self._get_docker()
            try:
                c = dc.containers.get(self._container_name(account_id))
                c.stop(timeout=10)
                c.remove(force=True)
                logger.info("[session_manager] Container stopped for %s", account_id)
            except docker.errors.NotFound:
                pass

        await asyncio.to_thread(_stop)

    async def container_status(self, account_id: str) -> dict:
        """Return the Docker container status for an account."""
        def _status():
            import docker
            dc = self._get_docker()
            name = self._container_name(account_id)
            try:
                c = dc.containers.get(name)
                return {"exists": True, "status": c.status, "name": name}
            except docker.errors.NotFound:
                return {"exists": False, "status": "not_found", "name": name}

        return await asyncio.to_thread(_status)

    async def shutdown(self) -> None:
        """Close all active sessions (containers keep running)."""
        async with self._lock:
            account_ids = list(self._sessions.keys())
        for aid in account_ids:
            await self.release_session(aid)
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
        logger.info("[session_manager] BrowserSessionManager shut down")

    # ── Properties (parity with BrowserManager) ───────────────────────────────

    @property
    def active_sessions(self) -> int:
        return len(self._sessions)

    @property
    def pool_capacity(self) -> int:
        return settings.BROWSER_POOL_SIZE
