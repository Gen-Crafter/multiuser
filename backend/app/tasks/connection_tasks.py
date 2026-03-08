"""Connection growth campaign tasks – search, scrape, and send invites."""

from __future__ import annotations

import asyncio
import uuid

from app.tasks.celery_app import celery_app
from app.tasks.campaign_tasks import _run_async, _get_db_session, _get_rate_guard


@celery_app.task(name="app.tasks.connection_tasks.run_connection_campaign", queue="connections")
def run_connection_campaign(campaign_id: str):
    """Execute a full connection growth cycle: search → scrape → personalize → invite."""

    async def _run():
        from app.automation.anti_detection import ActivityDistributor, DelayEngine
        from app.automation.browser_manager import browser_manager
        from app.automation.linkedin_actions import LinkedInActions
        from app.models.campaign import Campaign, CampaignStatus
        from app.models.linkedin_account import LinkedInAccount, AccountStatus
        from app.services.campaign_engine import CampaignEngine
        from app.services.llm_service import llm_service
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
            # Check activity distribution
            # DISABLED FOR TESTING - re-enable after verifying campaigns work
            # if not ActivityDistributor.should_be_active(now.hour):
            #     return {"status": "skipped", "reason": "outside active hours"}

            # Get browser session
            actions = LinkedInActions(browser_manager)
            session = await browser_manager.get_session(
                str(account.id),
                encrypted_cookies=account.encrypted_cookies,
                fingerprint_config=account.fingerprint_config,
                proxy_url=account.proxy_url,
            )

            # Session check temporarily bypassed - proxy bandwidth exhausted,
            # cookies confirmed valid via httpx check. Re-enable after adding working proxy.
            # valid = await browser_manager.check_session_valid(str(account.id))
            # if not valid:
            #     await browser_manager.release_session(str(account.id))
            #     account.status = AccountStatus.SESSION_EXPIRED
            #     db.add(account)
            #     await db.commit()
            #     return {"status": "session_expired"}

            # Generate search keywords via LLM
            icp = campaign.icp_description or ""
            titles = campaign.target_job_titles or []
            industry = campaign.target_industry or ""
            geography = campaign.target_geography or ""

            keywords_prompt = (
                f"Generate 3 LinkedIn search keyword strings for finding people matching:\n"
                f"ICP: {icp}\nJob titles: {', '.join(titles)}\n"
                f"Industry: {industry}\nGeography: {geography}\n"
                f"Return only the keywords, one per line."
            )
            try:
                keywords_text = await llm_service.generate(keywords_prompt, temperature=0.5, max_tokens=200)
                search_keywords = [k.strip() for k in keywords_text.strip().splitlines() if k.strip()][:3]
            except Exception:
                search_keywords = []

            if not search_keywords:
                search_keywords = titles[:3] or [icp[:50]]

            # Search and collect leads
            all_leads = []
            batch_size = ActivityDistributor.get_batch_size(now.hour, max_batch=10)

            for kw in search_keywords:
                if len(all_leads) >= batch_size:
                    break

                # Rate check for profile views
                allowed, info = await rate_guard.can_perform(
                    str(account.id), RateAction.PROFILE_VIEW,
                    account.account_type.value, account.warmup_day,
                )
                if not allowed:
                    break

                filters = {}
                if industry:
                    filters["industry"] = industry
                if geography:
                    filters["location"] = geography

                search_results = await actions.search_people(
                    session, kw, filters=filters, max_results=batch_size - len(all_leads)
                )

                for sr in search_results:
                    await rate_guard.record_action(str(account.id), RateAction.PROFILE_VIEW)
                    all_leads.append(sr)
                    await DelayEngine.delay("between_profiles")

            # Scrape profiles and send connection requests
            engine = CampaignEngine(db, rate_guard)
            scraped_leads = []

            for lead_data in all_leads:
                # Rate check for connection request
                allowed, info = await rate_guard.can_perform(
                    str(account.id), RateAction.CONNECTION_REQUEST,
                    account.account_type.value, account.warmup_day,
                )
                if not allowed:
                    break

                # Scrape profile
                profile_url = lead_data.get("linkedin_url", "")
                if profile_url:
                    scraped = await actions.visit_and_scrape_profile(session, profile_url)
                    lead_data.update(scraped)
                    await DelayEngine.delay("between_profiles")

                scraped_leads.append(lead_data)

            # Generate personalized notes and send invites
            results = await engine.execute_connection_campaign(str(campaign.id), scraped_leads)

            # Send actual connection requests via browser
            sent_count = 0
            for detail in results.get("details", []):
                if detail.get("status") == "sent":
                    url = detail.get("lead_url", "")
                    note = detail.get("note", "")
                    if url:
                        send_result = await actions.send_connection_request(session, url, note)
                        if send_result["status"] in ("sent", "sent_with_note"):
                            sent_count += 1
                        await DelayEngine.delay("between_connections")

            await db.commit()
            await browser_manager.release_session(str(account.id))

            # Compute risk after batch
            await rate_guard.compute_risk(str(account.id), account.account_type.value)

            return {
                "status": "completed",
                "campaign_id": campaign_id,
                "searched": len(all_leads),
                "invites_sent": sent_count,
                "batch_size": batch_size,
            }

    return _run_async(_run())


@celery_app.task(name="app.tasks.connection_tasks.process_single_connection", queue="connections")
def process_single_connection(campaign_id: str, lead_data: dict):
    """Process a single connection request – scrape + personalize + invite."""

    async def _run():
        from app.automation.anti_detection import DelayEngine
        from app.automation.browser_manager import browser_manager
        from app.automation.linkedin_actions import LinkedInActions
        from app.models.campaign import Campaign
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

            # Rate check
            allowed, _ = await rate_guard.can_perform(
                str(account.id), RateAction.CONNECTION_REQUEST,
                account.account_type.value, account.warmup_day,
            )
            if not allowed:
                return {"status": "rate_limited"}

            actions = LinkedInActions(browser_manager)
            session = await browser_manager.get_session(
                str(account.id),
                encrypted_cookies=account.encrypted_cookies,
                fingerprint_config=account.fingerprint_config,
            )

            # Scrape
            profile_url = lead_data.get("linkedin_url", "")
            if profile_url:
                scraped = await actions.visit_and_scrape_profile(session, profile_url)
                lead_data.update(scraped)

            # Generate note and persist lead
            engine = CampaignEngine(db, rate_guard)
            result = await engine.execute_connection_campaign(str(campaign.id), [lead_data])

            # Send invite
            for detail in result.get("details", []):
                if detail.get("status") == "sent":
                    send_result = await actions.send_connection_request(
                        session, detail.get("lead_url", ""), detail.get("note", "")
                    )

            await db.commit()
            await browser_manager.release_session(str(account.id))
            return result

    return _run_async(_run())
