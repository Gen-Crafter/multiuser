"""Posting campaign tasks – scheduled post generation and publishing."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from app.tasks.celery_app import celery_app
from app.tasks.campaign_tasks import _run_async, _get_db_session, _get_rate_guard


@celery_app.task(name="app.tasks.posting_tasks.run_posting_campaign", queue="posting")
def run_posting_campaign(campaign_id: str):
    """Generate and publish an AI post for a campaign."""

    async def _run():
        from app.automation.browser_manager import browser_manager
        from app.automation.linkedin_actions import LinkedInActions
        from app.models.campaign import Campaign, CampaignStatus
        from app.models.linkedin_account import LinkedInAccount, AccountStatus
        from app.services.campaign_engine import CampaignEngine
        from app.services.rate_guard import RateGuardService
        from sqlalchemy import select

        db = await _get_db_session()
        rate_guard = await _get_rate_guard()
        async with db:
            result = await db.execute(
                select(Campaign).where(Campaign.id == uuid.UUID(campaign_id))
            )
            campaign = result.scalar_one_or_none()
            if not campaign or campaign.status != CampaignStatus.ACTIVE:
                return {"status": "skipped", "reason": "campaign not active"}

            # Get linked account
            acct_result = await db.execute(
                select(LinkedInAccount).where(LinkedInAccount.id == campaign.linkedin_account_id)
            )
            account = acct_result.scalar_one_or_none()
            if not account or account.status != AccountStatus.ACTIVE:
                return {"status": "skipped", "reason": "account not active"}

            # Generate post content via LLM
            engine = CampaignEngine(db, rate_guard)
            gen_result = await engine.execute_post_campaign(str(campaign.id))

            if gen_result["status"] != "generated":
                return gen_result

            post_content = gen_result["content"]

            # Publish via browser automation
            actions = LinkedInActions(browser_manager)
            session = await browser_manager.get_session(
                str(account.id),
                encrypted_cookies=account.encrypted_cookies,
                fingerprint_config=account.fingerprint_config,
            )

            # Verify session
            valid = await browser_manager.check_session_valid(str(account.id))
            if not valid:
                await browser_manager.release_session(str(account.id))
                account.status = AccountStatus.SESSION_EXPIRED
                db.add(account)
                await db.commit()
                return {"status": "session_expired"}

            publish_result = await actions.create_post(session, post_content)

            # Update campaign metrics
            if publish_result["status"] == "posted":
                campaign.total_sent += 1

            db.add(campaign)
            await db.commit()

            await browser_manager.release_session(str(account.id))
            return {
                "status": publish_result["status"],
                "campaign_id": campaign_id,
                "content_preview": post_content[:200],
            }

    return _run_async(_run())


@celery_app.task(name="app.tasks.posting_tasks.check_scheduled_posts", queue="posting")
def check_scheduled_posts():
    """Check all active posting campaigns and trigger if schedule matches."""

    async def _check():
        from app.models.campaign import Campaign, CampaignStatus, CampaignType
        from sqlalchemy import select

        db = await _get_db_session()
        async with db:
            result = await db.execute(
                select(Campaign).where(
                    Campaign.campaign_type == CampaignType.POST_GENERATOR,
                    Campaign.status == CampaignStatus.ACTIVE,
                )
            )
            campaigns = result.scalars().all()
            triggered = 0

            now = datetime.now(timezone.utc)
            for campaign in campaigns:
                schedule = campaign.posting_schedule or {}
                # Simple schedule check: hours list or interval_hours
                hours = schedule.get("hours", [])
                interval = schedule.get("interval_hours", 24)

                should_post = False
                if hours and now.hour in hours:
                    should_post = True
                elif interval:
                    # Check if enough time since last post
                    last_post_delta = (now - campaign.updated_at).total_seconds() / 3600
                    if last_post_delta >= interval:
                        should_post = True

                if should_post:
                    run_posting_campaign.delay(str(campaign.id))
                    triggered += 1

            return {"checked": len(campaigns), "triggered": triggered}

    return _run_async(_check())
