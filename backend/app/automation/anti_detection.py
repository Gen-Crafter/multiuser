"""Anti-detection utilities – human-like delays, fingerprint randomization, typing simulation."""

from __future__ import annotations

import asyncio
import random
from typing import Optional

from fake_useragent import UserAgent


# ── Delay Engine ────────────────────────────────────────────
class DelayEngine:
    """Generates human-like random delays between actions."""

    # Delay ranges in seconds (min, max) for different action types
    PROFILES = {
        "page_load": (2.0, 5.0),
        "between_actions": (1.5, 4.0),
        "typing_char": (0.05, 0.15),
        "before_click": (0.5, 1.5),
        "after_click": (1.0, 3.0),
        "scroll_pause": (0.8, 2.5),
        "between_profiles": (5.0, 15.0),
        "between_messages": (30.0, 90.0),
        "between_connections": (20.0, 60.0),
        "session_break": (300.0, 900.0),
    }

    @classmethod
    async def delay(cls, action_type: str = "between_actions", multiplier: float = 1.0):
        """Sleep for a human-like random duration."""
        lo, hi = cls.PROFILES.get(action_type, (1.0, 3.0))
        duration = random.uniform(lo, hi) * multiplier
        # Add occasional micro-variance
        if random.random() < 0.15:
            duration += random.uniform(0.5, 2.0)
        await asyncio.sleep(duration)

    @classmethod
    async def typing_delay(cls, text: str, page) -> None:
        """Simulate human typing with variable speed."""
        for char in text:
            await page.keyboard.type(char, delay=random.randint(50, 150))
            # Occasional pause as if thinking
            if random.random() < 0.05:
                await asyncio.sleep(random.uniform(0.3, 1.0))


# ── Fingerprint Randomizer ──────────────────────────────────
class FingerprintRandomizer:
    """Generates randomized browser fingerprint configurations."""

    _ua = UserAgent()

    VIEWPORTS = [
        {"width": 1920, "height": 1080},
        {"width": 1366, "height": 768},
        {"width": 1440, "height": 900},
        {"width": 1536, "height": 864},
        {"width": 1280, "height": 720},
        {"width": 2560, "height": 1440},
        {"width": 1600, "height": 900},
    ]

    TIMEZONES = [
        "America/New_York",
        "America/Chicago",
        "America/Denver",
        "America/Los_Angeles",
        "Europe/London",
        "Europe/Berlin",
        "Asia/Tokyo",
        "Asia/Kolkata",
        "Australia/Sydney",
    ]

    LOCALES = ["en-US", "en-GB", "en-AU", "en-CA"]

    @classmethod
    def generate(cls, base_config: Optional[dict] = None) -> dict:
        """Generate a randomized fingerprint configuration."""
        config = base_config or {}
        viewport = random.choice(cls.VIEWPORTS)
        return {
            "user_agent": config.get("user_agent", cls._ua.chrome),
            "viewport": config.get("viewport", viewport),
            "timezone_id": config.get("timezone_id", random.choice(cls.TIMEZONES)),
            "locale": config.get("locale", random.choice(cls.LOCALES)),
            "color_scheme": random.choice(["light", "dark"]),
            "device_scale_factor": random.choice([1, 1.25, 1.5, 2]),
            "has_touch": False,
            "is_mobile": False,
            "extra_headers": {
                "Accept-Language": f"{random.choice(cls.LOCALES)},en;q=0.9",
            },
        }


# ── Activity Distribution ──────────────────────────────────
class ActivityDistributor:
    """Distributes daily actions across working hours to mimic human patterns."""

    # Activity weight by hour (0-23). Higher = more activity.
    HOUR_WEIGHTS = {
        0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0,
        6: 0.1, 7: 0.3, 8: 0.7, 9: 1.0, 10: 1.0,
        11: 0.8, 12: 0.4, 13: 0.6, 14: 0.9, 15: 1.0,
        16: 0.9, 17: 0.7, 18: 0.4, 19: 0.2, 20: 0.1,
        21: 0.05, 22: 0, 23: 0,
    }

    @classmethod
    def should_be_active(cls, hour: int) -> bool:
        """Probabilistically decide if the system should be active at this hour."""
        weight = cls.HOUR_WEIGHTS.get(hour, 0)
        return random.random() < weight

    @classmethod
    def get_batch_size(cls, hour: int, max_batch: int = 10) -> int:
        """Get recommended batch size for the current hour."""
        weight = cls.HOUR_WEIGHTS.get(hour, 0)
        return max(1, int(max_batch * weight))

    @classmethod
    def distribute_actions(cls, total_actions: int, timezone_offset: int = 0) -> dict[int, int]:
        """Distribute N actions across hours of the day."""
        weights = {}
        total_weight = 0
        for h in range(24):
            adjusted_hour = (h + timezone_offset) % 24
            w = cls.HOUR_WEIGHTS.get(adjusted_hour, 0)
            weights[h] = w
            total_weight += w

        if total_weight == 0:
            return {9: total_actions}

        distribution = {}
        remaining = total_actions
        for h, w in weights.items():
            if w > 0:
                count = max(0, round(total_actions * (w / total_weight)))
                distribution[h] = min(count, remaining)
                remaining -= distribution[h]
            if remaining <= 0:
                break

        return distribution


# ── Shadow-ban Detection ────────────────────────────────────
class ShadowBanDetector:
    """Heuristics to detect potential LinkedIn shadow-bans or restrictions."""

    @staticmethod
    async def check_signals(page) -> dict:
        """Check the current page for shadow-ban signals."""
        signals = {
            "restricted": False,
            "search_limited": False,
            "connection_blocked": False,
            "message_blocked": False,
            "signals": [],
        }

        try:
            # Check for restriction banners
            restriction_selectors = [
                '[data-test="restriction-message"]',
                '.restricted-profile',
                '[class*="restriction"]',
                '[class*="suspended"]',
            ]
            for selector in restriction_selectors:
                element = await page.query_selector(selector)
                if element:
                    signals["restricted"] = True
                    signals["signals"].append(f"Found restriction element: {selector}")

            # Check for CAPTCHA
            captcha_selectors = [
                '#captcha-challenge',
                '[class*="captcha"]',
                'iframe[src*="captcha"]',
            ]
            for selector in captcha_selectors:
                element = await page.query_selector(selector)
                if element:
                    signals["restricted"] = True
                    signals["signals"].append("CAPTCHA detected")

            # Check page title for error indicators
            title = await page.title()
            if "security" in title.lower() or "verify" in title.lower():
                signals["restricted"] = True
                signals["signals"].append(f"Suspicious page title: {title}")

        except Exception as e:
            signals["signals"].append(f"Detection error: {str(e)}")

        return signals


# ── Warm-up Mode ────────────────────────────────────────────
class WarmupSchedule:
    """Manages gradual account warm-up over 7 days."""

    # day -> max percentage of normal limits
    SCHEDULE = {
        0: 0.10,
        1: 0.15,
        2: 0.20,
        3: 0.30,
        4: 0.40,
        5: 0.50,
        6: 0.70,
        7: 1.00,
    }

    @classmethod
    def get_multiplier(cls, warmup_day: int) -> float:
        return cls.SCHEDULE.get(min(warmup_day, 7), 1.0)

    @classmethod
    def get_recommended_actions(cls, warmup_day: int) -> dict:
        mult = cls.get_multiplier(warmup_day)
        return {
            "profile_views": max(1, int(10 * mult)),
            "connections": max(0, int(5 * mult)),
            "messages": max(0, int(3 * mult)),
            "posts": 1 if warmup_day >= 2 else 0,
            "feed_scrolls": max(3, int(15 * mult)),
        }
