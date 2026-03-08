"""LinkedIn browser automation actions – login, search, connect, message, post, scrape."""

from __future__ import annotations

import asyncio
import json
import random
from typing import Any, Optional

from playwright.async_api import Page

from app.automation.anti_detection import DelayEngine, ShadowBanDetector
from app.automation.browser_manager import BrowserManager, BrowserSession
from app.security import decrypt_value

LINKEDIN_BASE = "https://www.linkedin.com"


class LinkedInActions:
    """High-level LinkedIn automation actions using Playwright."""

    def __init__(self, browser_manager: BrowserManager):
        self.bm = browser_manager

    # ── Login ───────────────────────────────────────────
    async def login(
        self,
        account_id: str,
        encrypted_password: str,
        linkedin_email: str,
        encrypted_cookies: Optional[str] = None,
        fingerprint_config: Optional[dict] = None,
        proxy_url: Optional[str] = None,
    ) -> dict[str, Any]:
        """Login to LinkedIn and store session cookies."""
        session = await self.bm.get_session(account_id, encrypted_cookies, fingerprint_config, proxy_url)
        page = session.page

        # Try session restore first
        if encrypted_cookies:
            valid = await self.bm.check_session_valid(account_id)
            if valid:
                cookies = await self.bm.save_session_cookies(account_id)
                return {"status": "restored", "encrypted_cookies": cookies}

        # Full login
        try:
            await page.goto(f"{LINKEDIN_BASE}/login", wait_until="domcontentloaded", timeout=30000)
            await DelayEngine.delay("page_load")

            # Fill email
            email_input = await page.wait_for_selector('#username', timeout=10000)
            await email_input.click()
            await DelayEngine.delay("before_click")
            await DelayEngine.typing_delay(linkedin_email, page)

            # Fill password
            password = decrypt_value(encrypted_password)
            pwd_input = await page.wait_for_selector('#password', timeout=10000)
            await pwd_input.click()
            await DelayEngine.delay("before_click")
            await DelayEngine.typing_delay(password, page)

            # Click sign in
            await DelayEngine.delay("before_click")
            await page.click('button[type="submit"]')
            await DelayEngine.delay("page_load")

            # Wait for navigation
            await page.wait_for_load_state("domcontentloaded", timeout=30000)

            # Check for challenge/verification
            url = page.url
            if "/checkpoint" in url or "/challenge" in url:
                return {"status": "verification_required", "url": url}

            if "/feed" in url or "/mynetwork" in url:
                cookies = await self.bm.save_session_cookies(account_id)
                return {"status": "success", "encrypted_cookies": cookies}

            return {"status": "unknown", "url": url}

        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ── Search People ───────────────────────────────────
    async def search_people(
        self,
        session: BrowserSession,
        keywords: str,
        filters: Optional[dict] = None,
        max_results: int = 25,
    ) -> list[dict]:
        """Search LinkedIn for people matching criteria."""
        page = session.page
        results = []

        try:
            # Build search URL
            search_url = f"{LINKEDIN_BASE}/search/results/people/?keywords={keywords}"
            if filters:
                if filters.get("industry"):
                    search_url += f"&industry={filters['industry']}"
                if filters.get("location"):
                    search_url += f"&geoUrn={filters['location']}"
                if filters.get("title"):
                    search_url += f"&title={filters['title']}"

            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await DelayEngine.delay("page_load")

            page_num = 1
            while len(results) < max_results:
                # Scroll to load results
                for _ in range(3):
                    await page.evaluate("window.scrollBy(0, 500)")
                    await DelayEngine.delay("scroll_pause")

                # Extract results
                cards = await page.query_selector_all('.reusable-search__result-container')
                for card in cards:
                    if len(results) >= max_results:
                        break

                    try:
                        profile = await self._extract_search_result(card)
                        if profile and profile.get("linkedin_url"):
                            results.append(profile)
                    except Exception:
                        continue

                # Next page
                page_num += 1
                next_btn = await page.query_selector('button[aria-label="Next"]')
                if not next_btn or len(results) >= max_results:
                    break

                await next_btn.click()
                await DelayEngine.delay("page_load")

        except Exception as e:
            pass

        return results

    # ── Visit Profile & Scrape ──────────────────────────
    async def visit_and_scrape_profile(self, session: BrowserSession, profile_url: str) -> dict[str, Any]:
        """Visit a LinkedIn profile and extract data."""
        page = session.page

        try:
            await page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
            await DelayEngine.delay("page_load")

            # Scroll down to load content
            for _ in range(4):
                await page.evaluate("window.scrollBy(0, 600)")
                await DelayEngine.delay("scroll_pause")

            # Scroll back up
            await page.evaluate("window.scrollTo(0, 0)")
            await DelayEngine.delay("scroll_pause")

            profile = {}

            # Name
            name_el = await page.query_selector('h1.text-heading-xlarge')
            if name_el:
                profile["name"] = (await name_el.inner_text()).strip()

            # Headline
            headline_el = await page.query_selector('.text-body-medium.break-words')
            if headline_el:
                profile["headline"] = (await headline_el.inner_text()).strip()

            # Location
            location_el = await page.query_selector('.text-body-small.inline.t-black--light.break-words')
            if location_el:
                profile["location"] = (await location_el.inner_text()).strip()

            # About section
            about_el = await page.query_selector('#about ~ .display-flex .inline-show-more-text')
            if about_el:
                profile["about"] = (await about_el.inner_text()).strip()

            # Current experience
            exp_section = await page.query_selector('#experience ~ .pvs-list__outer-container')
            if exp_section:
                exp_items = await exp_section.query_selector_all('.pvs-entity--padded')
                experiences = []
                for item in exp_items[:3]:
                    try:
                        title_el = await item.query_selector('.t-bold span')
                        company_el = await item.query_selector('.t-normal span')
                        title_text = (await title_el.inner_text()).strip() if title_el else ""
                        company_text = (await company_el.inner_text()).strip() if company_el else ""
                        experiences.append({"title": title_text, "company": company_text})
                    except Exception:
                        continue
                profile["experiences"] = experiences

            # Connection count
            conn_el = await page.query_selector('li.text-body-small span.t-bold')
            if conn_el:
                profile["connections"] = (await conn_el.inner_text()).strip()

            profile["linkedin_url"] = profile_url
            profile["scraped"] = True

            # Check for shadow-ban signals while we're here
            ban_signals = await ShadowBanDetector.check_signals(page)
            profile["_ban_signals"] = ban_signals

            return profile

        except Exception as e:
            return {"linkedin_url": profile_url, "error": str(e), "scraped": False}

    # ── Send Connection Request ─────────────────────────
    async def send_connection_request(
        self,
        session: BrowserSession,
        profile_url: str,
        note: Optional[str] = None,
    ) -> dict[str, Any]:
        """Send a connection request with optional personalized note."""
        page = session.page

        try:
            await page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
            await DelayEngine.delay("page_load")

            # Find Connect button
            connect_btn = await page.query_selector('button[aria-label*="Connect"]')
            if not connect_btn:
                # Try More menu
                more_btn = await page.query_selector('button[aria-label="More actions"]')
                if more_btn:
                    await more_btn.click()
                    await DelayEngine.delay("after_click")
                    connect_btn = await page.query_selector('div[aria-label*="Connect"]')

            if not connect_btn:
                return {"status": "connect_button_not_found", "url": profile_url}

            await connect_btn.click()
            await DelayEngine.delay("after_click")

            # Add note if provided
            if note:
                add_note_btn = await page.query_selector('button[aria-label="Add a note"]')
                if add_note_btn:
                    await add_note_btn.click()
                    await DelayEngine.delay("after_click")

                    textarea = await page.query_selector('#custom-message')
                    if textarea:
                        await textarea.click()
                        await DelayEngine.typing_delay(note[:300], page)  # LinkedIn limit: 300 chars

                    send_btn = await page.query_selector('button[aria-label="Send invitation"]')
                    if send_btn:
                        await send_btn.click()
                        await DelayEngine.delay("after_click")
                        return {"status": "sent_with_note", "url": profile_url}
            else:
                # Send without note
                send_btn = await page.query_selector('button[aria-label="Send without a note"]')
                if not send_btn:
                    send_btn = await page.query_selector('button[aria-label="Send invitation"]')
                if send_btn:
                    await send_btn.click()
                    await DelayEngine.delay("after_click")
                    return {"status": "sent", "url": profile_url}

            return {"status": "send_failed", "url": profile_url}

        except Exception as e:
            return {"status": "error", "url": profile_url, "error": str(e)}

    # ── Send Message ────────────────────────────────────
    async def send_message(
        self,
        session: BrowserSession,
        profile_url: str,
        message: str,
    ) -> dict[str, Any]:
        """Send a direct message to a connected LinkedIn user."""
        page = session.page

        try:
            await page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
            await DelayEngine.delay("page_load")

            # Click Message button
            msg_btn = await page.query_selector('button[aria-label*="Message"]')
            if not msg_btn:
                return {"status": "message_button_not_found", "url": profile_url}

            await msg_btn.click()
            await DelayEngine.delay("after_click")

            # Wait for message box
            msg_box = await page.wait_for_selector('.msg-form__contenteditable', timeout=10000)
            if not msg_box:
                return {"status": "message_box_not_found", "url": profile_url}

            await msg_box.click()
            await DelayEngine.delay("before_click")
            await DelayEngine.typing_delay(message, page)
            await DelayEngine.delay("before_click")

            # Click send
            send_btn = await page.query_selector('button[aria-label="Send"]')
            if send_btn:
                await send_btn.click()
                await DelayEngine.delay("after_click")
                return {"status": "sent", "url": profile_url}

            return {"status": "send_failed", "url": profile_url}

        except Exception as e:
            return {"status": "error", "url": profile_url, "error": str(e)}

    # ── Create Post ─────────────────────────────────────
    async def create_post(self, session: BrowserSession, content: str) -> dict[str, Any]:
        """Create a LinkedIn post."""
        page = session.page

        try:
            await page.goto(f"{LINKEDIN_BASE}/feed/", wait_until="domcontentloaded", timeout=30000)
            await DelayEngine.delay("page_load")

            # Click "Start a post"
            start_post = await page.query_selector('button[aria-label*="Start a post"]')
            if not start_post:
                start_post = await page.query_selector('.share-box-feed-entry__trigger')

            if not start_post:
                return {"status": "start_post_not_found"}

            await start_post.click()
            await DelayEngine.delay("after_click")

            # Wait for editor
            editor = await page.wait_for_selector('.ql-editor, [contenteditable="true"]', timeout=10000)
            if not editor:
                return {"status": "editor_not_found"}

            await editor.click()
            await DelayEngine.delay("before_click")
            await DelayEngine.typing_delay(content, page)
            await DelayEngine.delay("between_actions")

            # Click Post button
            post_btn = await page.query_selector('button[aria-label*="Post"]')
            if not post_btn:
                post_btn = await page.query_selector('.share-actions__primary-action')

            if post_btn:
                await post_btn.click()
                await DelayEngine.delay("after_click")
                return {"status": "posted"}

            return {"status": "post_button_not_found"}

        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ── Check Inbox for Replies ─────────────────────────
    async def check_inbox(self, session: BrowserSession, max_conversations: int = 20) -> list[dict]:
        """Check LinkedIn messaging inbox for new replies."""
        page = session.page
        messages = []

        try:
            await page.goto(f"{LINKEDIN_BASE}/messaging/", wait_until="domcontentloaded", timeout=30000)
            await DelayEngine.delay("page_load")

            # Get conversation threads
            threads = await page.query_selector_all('.msg-conversation-listitem')
            for thread in threads[:max_conversations]:
                try:
                    name_el = await thread.query_selector('.msg-conversation-listitem__participant-names')
                    preview_el = await thread.query_selector('.msg-conversation-card__message-snippet-body')
                    time_el = await thread.query_selector('.msg-conversation-listitem__time-stamp')

                    unread_badge = await thread.query_selector('.notification-badge')

                    name = (await name_el.inner_text()).strip() if name_el else ""
                    preview = (await preview_el.inner_text()).strip() if preview_el else ""
                    timestamp = (await time_el.inner_text()).strip() if time_el else ""
                    is_unread = unread_badge is not None

                    if is_unread:
                        messages.append({
                            "name": name,
                            "preview": preview,
                            "timestamp": timestamp,
                            "unread": True,
                        })
                except Exception:
                    continue

        except Exception:
            pass

        return messages

    # ── Helper: Extract search result ───────────────────
    async def _extract_search_result(self, card) -> Optional[dict]:
        result = {}

        link = await card.query_selector('a[href*="/in/"]')
        if link:
            href = await link.get_attribute("href")
            result["linkedin_url"] = href.split("?")[0] if href else ""

        name_el = await card.query_selector('.entity-result__title-text a span[aria-hidden="true"]')
        if name_el:
            result["name"] = (await name_el.inner_text()).strip()

        headline_el = await card.query_selector('.entity-result__primary-subtitle')
        if headline_el:
            result["headline"] = (await headline_el.inner_text()).strip()

        location_el = await card.query_selector('.entity-result__secondary-subtitle')
        if location_el:
            result["location"] = (await location_el.inner_text()).strip()

        return result if result.get("linkedin_url") else None
