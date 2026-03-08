"""Campaign scheduler tasks - auto-run all active campaigns on a schedule."""

from __future__ import annotations

import uuid

from app.tasks.celery_app import celery_app
from app.tasks.campaign_tasks import _run_async, _get_db_session


@celery_app.task(name="app.tasks.connection_tasks.run_all_active_connection_campaigns", queue="campaigns")
def run_all_active_connection_campaigns():
    """Find all active connection campaigns and queue them for execution."""

    async def _run():
        from app.models.campaign import Campaign, CampaignStatus, CampaignType
        from app.models.linkedin_account import AccountStatus
        from app.tasks.connection_tasks import run_connection_campaign
        from sqlalchemy import select

        db = await _get_db_session()
        async with db:
            result = await db.execute(
                select(Campaign)
                .where(
                    Campaign.status == CampaignStatus.ACTIVE,
                    Campaign.campaign_type == CampaignType.CONNECTION_GROWTH,
                )
            )
            campaigns = result.scalars().all()

            queued = 0
            for campaign in campaigns:
                acct_result = await db.execute(
                    select(AccountStatus)
                    .select_from(Campaign)
                    .join(Campaign.linkedin_account)
                    .where(Campaign.id == campaign.id)
                )
                account_status = acct_result.scalar_one_or_none()
                if account_status == AccountStatus.ACTIVE:
                    run_connection_campaign.delay(str(campaign.id))
                    queued += 1

            return {"queued": queued, "total": len(campaigns)}

    return _run_async(_run())


@celery_app.task(name="app.tasks.sales_tasks.run_all_active_sales_campaigns", queue="campaigns")
def run_all_active_sales_campaigns():
    """Find all active sales campaigns and queue them for execution."""

    async def _run():
        from app.models.campaign import Campaign, CampaignStatus, CampaignType
        from app.models.linkedin_account import AccountStatus
        from app.tasks.sales_tasks import run_sales_campaign
        from sqlalchemy import select

        db = await _get_db_session()
        async with db:
            result = await db.execute(
                select(Campaign)
                .where(
                    Campaign.status == CampaignStatus.ACTIVE,
                    Campaign.campaign_type == CampaignType.SALES_OUTREACH,
                )
            )
            campaigns = result.scalars().all()

            queued = 0
            for campaign in campaigns:
                acct_result = await db.execute(
                    select(AccountStatus)
                    .select_from(Campaign)
                    .join(Campaign.linkedin_account)
                    .where(Campaign.id == campaign.id)
                )
                account_status = acct_result.scalar_one_or_none()
                if account_status == AccountStatus.ACTIVE:
                    run_sales_campaign.delay(str(campaign.id))
                    queued += 1

            return {"queued": queued, "total": len(campaigns)}

    return _run_async(_run())
