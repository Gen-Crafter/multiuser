"""Sales outreach campaign tasks – lead discovery, messaging, reply processing."""

from __future__ import annotations

import asyncio
import uuid

from app.tasks.celery_app import celery_app
from app.tasks.campaign_tasks import _run_async, _get_db_session, _get_rate_guard


@celery_app.task(name="app.tasks.sales_tasks.run_sales_campaign", queue="sales")
def run_sales_campaign(campaign_id: str):
    """Execute a sales outreach cycle: discover leads → analyze → send first messages."""

    async def _run():
        from app.automation.anti_detection import ActivityDistributor, DelayEngine
        from app.automation.browser_manager import browser_manager
        from app.automation.linkedin_actions import LinkedInActions
        from app.models.campaign import Campaign, CampaignStatus
        from app.models.lead import Lead, LeadStatus
        from app.models.linkedin_account import LinkedInAccount, AccountStatus
        from app.services.campaign_engine import CampaignEngine
        from app.services.rate_guard import RateAction
        from sqlalchemy import select
        from datetime import datetime, timezone

        db = await _get_db_session()
        rate_guard = await _get_rate_guard()
        async with db:
            result = await db.execute(
                select(Campaign).where(Campaign.id == uuid.UUID(campaign_id))
            )
            campaign = result.scalar_one_or_none()
            if not campaign or campaign.status != CampaignStatus.ACTIVE:
                return {"status": "skipped", "reason": "campaign not active"}

            acct_result = await db.execute(
                select(LinkedInAccount).where(LinkedInAccount.id == campaign.linkedin_account_id)
            )
            account = acct_result.scalar_one_or_none()
            if not account or account.status != AccountStatus.ACTIVE:
                return {"status": "skipped", "reason": "account not active"}

            now = datetime.now(timezone.utc)
            if not ActivityDistributor.should_be_active(now.hour):
                return {"status": "skipped", "reason": "outside active hours"}

            actions = LinkedInActions(browser_manager)
            session = await browser_manager.get_session(
                str(account.id),
                encrypted_cookies=account.encrypted_cookies,
                fingerprint_config=account.fingerprint_config,
            )

            valid = await browser_manager.check_session_valid(str(account.id))
            if not valid:
                await browser_manager.release_session(str(account.id))
                account.status = AccountStatus.SESSION_EXPIRED
                db.add(account)
                await db.commit()
                return {"status": "session_expired"}

            engine = CampaignEngine(db, rate_guard)

            # Phase 1: Find leads that are connected but not yet messaged
            leads_result = await db.execute(
                select(Lead).where(
                    Lead.campaign_id == campaign.id,
                    Lead.status == LeadStatus.CONNECTED,
                ).limit(ActivityDistributor.get_batch_size(now.hour, max_batch=5))
            )
            connected_leads = leads_result.scalars().all()

            messages_sent = 0
            for lead in connected_leads:
                allowed, info = await rate_guard.can_perform(
                    str(account.id), RateAction.MESSAGE,
                    account.account_type.value, account.warmup_day,
                )
                if not allowed:
                    break

                # Execute sales outreach (LLM analysis + first message)
                outreach_result = await engine.execute_sales_outreach(
                    str(campaign.id), str(lead.id)
                )

                if outreach_result.get("status") == "sent":
                    # Send via browser
                    send_result = await actions.send_message(
                        session, lead.linkedin_url, outreach_result["message"]
                    )
                    if send_result["status"] == "sent":
                        messages_sent += 1
                    await DelayEngine.delay("between_messages")

            # Phase 2: Check inbox for new replies
            inbox = await actions.check_inbox(session, max_conversations=20)
            replies_processed = 0

            for msg in inbox:
                if msg.get("unread"):
                    # Try to match with existing lead
                    lead_match = await db.execute(
                        select(Lead).where(
                            Lead.campaign_id == campaign.id,
                            Lead.linkedin_name == msg.get("name"),
                        )
                    )
                    lead = lead_match.scalar_one_or_none()
                    if lead:
                        reply_result = await engine.process_reply(
                            str(lead.id), msg.get("preview", "")
                        )
                        replies_processed += 1

            await db.commit()
            await browser_manager.release_session(str(account.id))

            await rate_guard.compute_risk(str(account.id), account.account_type.value)

            return {
                "status": "completed",
                "campaign_id": campaign_id,
                "messages_sent": messages_sent,
                "replies_processed": replies_processed,
            }

    return _run_async(_run())


@celery_app.task(name="app.tasks.sales_tasks.process_lead_outreach", queue="sales")
def process_lead_outreach(campaign_id: str, lead_id: str):
    """Process a single lead through the sales pipeline."""

    async def _run():
        from app.automation.anti_detection import DelayEngine
        from app.automation.browser_manager import browser_manager
        from app.automation.linkedin_actions import LinkedInActions
        from app.models.campaign import Campaign
        from app.models.lead import Lead
        from app.models.linkedin_account import LinkedInAccount, AccountStatus
        from app.services.campaign_engine import CampaignEngine
        from app.services.rate_guard import RateAction
        from sqlalchemy import select

        db = await _get_db_session()
        rate_guard = await _get_rate_guard()
        async with db:
            result = await db.execute(
                select(Campaign).where(Campaign.id == uuid.UUID(campaign_id))
            )
            campaign = result.scalar_one_or_none()
            if not campaign:
                return {"status": "error", "reason": "campaign not found"}

            acct_result = await db.execute(
                select(LinkedInAccount).where(LinkedInAccount.id == campaign.linkedin_account_id)
            )
            account = acct_result.scalar_one_or_none()
            if not account or account.status != AccountStatus.ACTIVE:
                return {"status": "skipped"}

            allowed, _ = await rate_guard.can_perform(
                str(account.id), RateAction.MESSAGE,
                account.account_type.value, account.warmup_day,
            )
            if not allowed:
                return {"status": "rate_limited"}

            engine = CampaignEngine(db, rate_guard)
            outreach_result = await engine.execute_sales_outreach(str(campaign.id), lead_id)

            if outreach_result.get("status") == "sent":
                actions = LinkedInActions(browser_manager)
                session = await browser_manager.get_session(
                    str(account.id),
                    encrypted_cookies=account.encrypted_cookies,
                    fingerprint_config=account.fingerprint_config,
                )

                lead_result = await db.execute(
                    select(Lead).where(Lead.id == uuid.UUID(lead_id))
                )
                lead = lead_result.scalar_one_or_none()
                if lead:
                    await actions.send_message(session, lead.linkedin_url, outreach_result["message"])
                    await DelayEngine.delay("between_messages")

                await browser_manager.release_session(str(account.id))

            await db.commit()
            return outreach_result

    return _run_async(_run())
