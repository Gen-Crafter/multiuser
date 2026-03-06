"""Rate Guard Service – Redis-based rate limiting with adaptive throttling."""

from __future__ import annotations

import time
from datetime import date, datetime, timezone
from typing import Optional

import redis.asyncio as aioredis

from app.config import get_settings

settings = get_settings()


class RateAction:
    CONNECTION_REQUEST = "connection_request"
    MESSAGE = "message"
    PROFILE_VIEW = "profile_view"
    POST = "post"


# Default daily limits by account type
LIMITS = {
    "normal": {
        RateAction.CONNECTION_REQUEST: settings.DEFAULT_CONNECTIONS_PER_DAY,
        RateAction.MESSAGE: settings.DEFAULT_MESSAGES_PER_DAY,
        RateAction.PROFILE_VIEW: settings.DEFAULT_PROFILE_VIEWS_PER_DAY,
        RateAction.POST: settings.DEFAULT_POSTS_PER_DAY,
    },
    "premium": {
        RateAction.CONNECTION_REQUEST: settings.PREMIUM_CONNECTIONS_PER_DAY,
        RateAction.MESSAGE: settings.PREMIUM_MESSAGES_PER_DAY,
        RateAction.PROFILE_VIEW: settings.PREMIUM_PROFILE_VIEWS_PER_DAY,
        RateAction.POST: settings.PREMIUM_POSTS_PER_DAY,
    },
}

# Warmup multipliers (day 0-7)
WARMUP_MULTIPLIERS = [0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.7, 1.0]


class RateGuardService:
    """Manages per-account rate limits with Redis counters."""

    def __init__(self, redis: aioredis.Redis):
        self.redis = redis

    def _key(self, account_id: str, action: str) -> str:
        today = date.today().isoformat()
        return f"rate:{account_id}:{action}:{today}"

    def _cooldown_key(self, account_id: str) -> str:
        return f"cooldown:{account_id}"

    def _suspension_key(self, account_id: str) -> str:
        return f"suspension:{account_id}"

    def _risk_key(self, account_id: str) -> str:
        return f"risk:{account_id}"

    # ── Get effective limit ─────────────────────────────
    def get_limit(self, account_type: str, action: str, warmup_day: int = 7) -> int:
        base = LIMITS.get(account_type, LIMITS["normal"]).get(action, 0)
        multiplier = WARMUP_MULTIPLIERS[min(warmup_day, len(WARMUP_MULTIPLIERS) - 1)]
        return max(1, int(base * multiplier))

    # ── Check if action is allowed ──────────────────────
    async def can_perform(
        self,
        account_id: str,
        action: str,
        account_type: str = "normal",
        warmup_day: int = 7,
    ) -> tuple[bool, dict]:
        # Check cooldown
        if await self.redis.exists(self._cooldown_key(account_id)):
            ttl = await self.redis.ttl(self._cooldown_key(account_id))
            return False, {"reason": "cooldown", "retry_after_seconds": ttl}

        # Check suspension
        if await self.redis.exists(self._suspension_key(account_id)):
            return False, {"reason": "suspended"}

        key = self._key(account_id, action)
        current = int(await self.redis.get(key) or 0)
        limit = self.get_limit(account_type, action, warmup_day)

        if current >= limit:
            return False, {
                "reason": "limit_reached",
                "current": current,
                "limit": limit,
                "action": action,
            }

        return True, {"current": current, "limit": limit, "remaining": limit - current}

    # ── Record an action ────────────────────────────────
    async def record_action(self, account_id: str, action: str) -> int:
        key = self._key(account_id, action)
        count = await self.redis.incr(key)
        # Set expiry to end of day (24h from first action)
        if count == 1:
            await self.redis.expire(key, 86400)
        return count

    # ── Get current usage ───────────────────────────────
    async def get_usage(self, account_id: str) -> dict:
        result = {}
        for action in [RateAction.CONNECTION_REQUEST, RateAction.MESSAGE, RateAction.PROFILE_VIEW, RateAction.POST]:
            key = self._key(account_id, action)
            result[action] = int(await self.redis.get(key) or 0)
        return result

    # ── Cooldown management ─────────────────────────────
    async def activate_cooldown(self, account_id: str, duration_seconds: int = 3600):
        await self.redis.setex(self._cooldown_key(account_id), duration_seconds, "1")

    async def is_in_cooldown(self, account_id: str) -> bool:
        return bool(await self.redis.exists(self._cooldown_key(account_id)))

    # ── Suspension detection ────────────────────────────
    async def flag_suspension(self, account_id: str):
        await self.redis.set(self._suspension_key(account_id), "1")

    async def clear_suspension(self, account_id: str):
        await self.redis.delete(self._suspension_key(account_id))

    # ── Risk score management ───────────────────────────
    async def update_risk_score(self, account_id: str, score: int):
        await self.redis.set(self._risk_key(account_id), str(min(100, max(0, score))))

    async def get_risk_score(self, account_id: str) -> int:
        val = await self.redis.get(self._risk_key(account_id))
        return int(val) if val else 0

    # ── Adaptive throttling ─────────────────────────────
    async def compute_risk(self, account_id: str, account_type: str = "normal") -> int:
        """Compute risk score based on usage patterns."""
        usage = await self.get_usage(account_id)
        risk = 0

        for action, count in usage.items():
            limit = LIMITS.get(account_type, LIMITS["normal"]).get(action, 1)
            ratio = count / max(limit, 1)
            if ratio > 0.9:
                risk += 30
            elif ratio > 0.7:
                risk += 15
            elif ratio > 0.5:
                risk += 5

        # Auto-cooldown at high risk
        if risk >= 70:
            await self.activate_cooldown(account_id, duration_seconds=7200)
        elif risk >= 50:
            await self.activate_cooldown(account_id, duration_seconds=1800)

        await self.update_risk_score(account_id, risk)
        return risk

    # ── Get all limits for an account ───────────────────
    async def get_limits_snapshot(self, account_id: str, account_type: str = "normal", warmup_day: int = 7) -> dict:
        usage = await self.get_usage(account_id)
        snapshot = {}
        for action in [RateAction.CONNECTION_REQUEST, RateAction.MESSAGE, RateAction.PROFILE_VIEW, RateAction.POST]:
            limit = self.get_limit(account_type, action, warmup_day)
            used = usage.get(action, 0)
            snapshot[action] = {"limit": limit, "used": used, "remaining": limit - used}
        return snapshot
