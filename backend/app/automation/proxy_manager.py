"""Proxy rotation manager for browser sessions."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Optional

from app.config import get_settings

settings = get_settings()


class ProxyManager:
    """Manages a pool of proxies with rotation and health tracking."""

    def __init__(self):
        self._proxies: list[dict] = []
        self._failed: dict[str, int] = {}  # proxy_url -> failure count
        self._assigned: dict[str, str] = {}  # account_id -> proxy_url

    def load_proxies(self, filepath: Optional[str] = None):
        """Load proxies from a text file. Format per line: protocol://user:pass@host:port"""
        path = Path(filepath or settings.PROXY_LIST_PATH)
        if not path.exists():
            return

        self._proxies = []
        for line in path.read_text().strip().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                self._proxies.append({
                    "server": line,
                    "healthy": True,
                    "uses": 0,
                })

    def get_proxy(self, account_id: Optional[str] = None) -> Optional[dict]:
        """Get a proxy, optionally sticky per account."""
        if not settings.PROXY_ROTATION_ENABLED or not self._proxies:
            return None

        # Return assigned proxy if exists and healthy
        if account_id and account_id in self._assigned:
            url = self._assigned[account_id]
            proxy = next((p for p in self._proxies if p["server"] == url and p["healthy"]), None)
            if proxy:
                return {"server": proxy["server"]}

        # Select a healthy proxy with least uses
        healthy = [p for p in self._proxies if p["healthy"]]
        if not healthy:
            # Reset all to healthy if none available
            for p in self._proxies:
                p["healthy"] = True
            healthy = self._proxies

        if not healthy:
            return None

        proxy = min(healthy, key=lambda p: p["uses"])
        proxy["uses"] += 1

        if account_id:
            self._assigned[account_id] = proxy["server"]

        return {"server": proxy["server"]}

    def report_failure(self, proxy_url: str):
        """Report a proxy failure. Mark unhealthy after 3 failures."""
        self._failed[proxy_url] = self._failed.get(proxy_url, 0) + 1
        if self._failed[proxy_url] >= 3:
            for p in self._proxies:
                if p["server"] == proxy_url:
                    p["healthy"] = False
                    break

    def report_success(self, proxy_url: str):
        """Reset failure count on success."""
        self._failed.pop(proxy_url, None)

    def release(self, account_id: str):
        """Release a sticky proxy assignment."""
        self._assigned.pop(account_id, None)

    @property
    def available_count(self) -> int:
        return len([p for p in self._proxies if p["healthy"]])

    @property
    def total_count(self) -> int:
        return len(self._proxies)

    def get_stats(self) -> dict:
        return {
            "total": self.total_count,
            "healthy": self.available_count,
            "assigned": len(self._assigned),
            "failed_proxies": {k: v for k, v in self._failed.items() if v > 0},
        }


# Singleton
proxy_manager = ProxyManager()
