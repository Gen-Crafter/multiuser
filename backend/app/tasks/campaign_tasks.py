"""General campaign tasks – login, analytics snapshots, warmup progression."""

from __future__ import annotations

import asyncio
import uuid

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.tasks.celery_app import celery_app


def _run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _get_db_session():
    from app.database import async_session_factory
    return async_session_factory()


async def _get_rate_guard():
    import redis.asyncio as aioredis
    from app.config import get_settings
    from app.services.rate_guard import RateGuardService
    settings = get_settings()
    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return RateGuardService(r)


@celery_app.task(name="app.tasks.campaign_tasks.linkedin_login_task", queue="campaigns")
def linkedin_login_task(account_id: str):
    """Perform LinkedIn login for an account via Playwright."""

    async def _login():
        from app.automation.browser_manager import browser_manager
        from app.automation.linkedin_actions import LinkedInActions
        from app.models.linkedin_account import LinkedInAccount, AccountStatus

        db = await _get_db_session()
        async with db:
            result = await db.execute(
                select(LinkedInAccount).where(LinkedInAccount.id == uuid.UUID(account_id))
            )
            account = result.scalar_one_or_none()
            if not account:
                return {"error": "account not found"}

            actions = LinkedInActions(browser_manager)
            login_result = await actions.login(
                account_id=str(account.id),
                encrypted_password=account.encrypted_password,
                linkedin_email=account.linkedin_email,
                encrypted_cookies=account.encrypted_cookies,
                fingerprint_config=account.fingerprint_config,
            )

            if login_result["status"] in ("success", "restored"):
                account.status = AccountStatus.ACTIVE
                account.encrypted_cookies = login_result.get("encrypted_cookies")
            elif login_result["status"] == "verification_required":
                account.status = AccountStatus.SESSION_EXPIRED
            else:
                account.status = AccountStatus.SESSION_EXPIRED

            db.add(account)
            await db.commit()

            await browser_manager.release_session(str(account.id))
            return login_result

    return _run_async(_login())


@celery_app.task(name="app.tasks.campaign_tasks.daily_analytics_snapshot", queue="campaigns")
def daily_analytics_snapshot():
    """Snapshot daily analytics for all active LinkedIn accounts."""

    async def _snapshot():
        from app.models.linkedin_account import LinkedInAccount, AccountStatus
        from app.services.analytics_service import AnalyticsService

        db = await _get_db_session()
        rate_guard = await _get_rate_guard()
        async with db:
            result = await db.execute(
                select(LinkedInAccount).where(LinkedInAccount.status == AccountStatus.ACTIVE)
            )
            accounts = result.scalars().all()

            analytics_svc = AnalyticsService(db, rate_guard)
            for account in accounts:
                try:
                    await analytics_svc.snapshot_daily_analytics(str(account.id))
                except Exception:
                    continue

            # Also snapshot all active campaigns
            from app.models.campaign import Campaign, CampaignStatus
            camp_result = await db.execute(
                select(Campaign).where(Campaign.status == CampaignStatus.ACTIVE)
            )
            campaigns = camp_result.scalars().all()
            for campaign in campaigns:
                try:
                    await analytics_svc.snapshot_campaign_analytics(str(campaign.id))
                    await analytics_svc.compute_llm_feedback(str(campaign.id))
                except Exception:
                    continue

            await db.commit()
            return {"accounts_processed": len(accounts), "campaigns_processed": len(campaigns)}

    return _run_async(_snapshot())


@celery_app.task(name="app.tasks.campaign_tasks.progress_warmup", queue="campaigns")
def progress_warmup():
    """Advance warmup day for accounts that are warming up."""

    async def _progress():
        from app.models.linkedin_account import LinkedInAccount

        db = await _get_db_session()
        async with db:
            result = await db.execute(
                select(LinkedInAccount).where(LinkedInAccount.is_warming_up == True)
            )
            accounts = result.scalars().all()
            progressed = 0

            for account in accounts:
                account.warmup_day += 1
                if account.warmup_day >= 7:
                    account.is_warming_up = False
                db.add(account)
                progressed += 1

            await db.commit()
            return {"progressed": progressed}

    return _run_async(_progress())
