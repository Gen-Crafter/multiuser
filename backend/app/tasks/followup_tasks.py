"""Follow-up automation tasks – periodic follow-up processing and sending."""

from __future__ import annotations

import asyncio
import uuid

from app.tasks.celery_app import celery_app
from app.tasks.campaign_tasks import _run_async, _get_db_session, _get_rate_guard


@celery_app.task(name="app.tasks.followup_tasks.process_pending_followups", queue="followups")
def process_pending_followups():
    """Find all conversations needing follow-up and dispatch individual tasks."""

    async def _run():
        from app.services.conversation_intelligence import ConversationIntelligenceService

        db = await _get_db_session()
        async with db:
            ci = ConversationIntelligenceService(db)
            candidates = await ci.get_followup_candidates()

            dispatched = 0
            for candidate in candidates:
                send_followup_message.delay(
                    candidate["conversation_id"],
                    candidate["lead_id"],
                )
                dispatched += 1

            return {"candidates_found": len(candidates), "dispatched": dispatched}

    return _run_async(_run())


@celery_app.task(name="app.tasks.followup_tasks.send_followup_message", queue="followups")
def send_followup_message(conversation_id: str, lead_id: str):
    """Generate and send a follow-up message for a specific conversation."""

    async def _run():
        from app.automation.anti_detection import DelayEngine
        from app.automation.browser_manager import browser_manager
        from app.automation.linkedin_actions import LinkedInActions
        from app.models.campaign import Campaign
        from app.models.lead import Lead
        from app.models.linkedin_account import LinkedInAccount, AccountStatus
        from app.services.conversation_intelligence import ConversationIntelligenceService
        from app.services.rate_guard import RateAction
        from sqlalchemy import select

        db = await _get_db_session()
        rate_guard = await _get_rate_guard()
        async with db:
            # Get lead and its campaign/account
            lead_result = await db.execute(
                select(Lead).where(Lead.id == uuid.UUID(lead_id))
            )
            lead = lead_result.scalar_one_or_none()
            if not lead:
                return {"status": "error", "reason": "lead not found"}

            campaign_result = await db.execute(
                select(Campaign).where(Campaign.id == lead.campaign_id)
            )
            campaign = campaign_result.scalar_one_or_none()
            if not campaign:
                return {"status": "error", "reason": "campaign not found"}

            # Check max followups
            if lead.followup_count >= campaign.max_followups:
                return {"status": "skipped", "reason": "max followups reached"}

            acct_result = await db.execute(
                select(LinkedInAccount).where(LinkedInAccount.id == campaign.linkedin_account_id)
            )
            account = acct_result.scalar_one_or_none()
            if not account or account.status != AccountStatus.ACTIVE:
                return {"status": "skipped", "reason": "account not active"}

            # Rate check
            allowed, info = await rate_guard.can_perform(
                str(account.id), RateAction.MESSAGE,
                account.account_type.value, account.warmup_day,
            )
            if not allowed:
                return {"status": "rate_limited", **info}

            # Generate follow-up via conversation intelligence
            ci = ConversationIntelligenceService(db)
            gen_result = await ci.generate_followup_message(conversation_id)

            if gen_result.get("status") != "generated":
                return gen_result

            followup_content = gen_result["content"]

            # Send via browser
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

            send_result = await actions.send_message(session, lead.linkedin_url, followup_content)

            if send_result["status"] == "sent":
                await rate_guard.record_action(str(account.id), RateAction.MESSAGE)

            await db.commit()
            await browser_manager.release_session(str(account.id))

            return {
                "status": send_result["status"],
                "conversation_id": conversation_id,
                "lead_id": lead_id,
                "followup_stage": gen_result.get("followup_stage"),
                "content_preview": followup_content[:150],
            }

    return _run_async(_run())


@celery_app.task(name="app.tasks.followup_tasks.process_reply_and_followup", queue="followups")
def process_reply_and_followup(lead_id: str, reply_content: str):
    """Process an inbound reply and decide on next action."""

    async def _run():
        from app.models.lead import Lead
        from app.models.conversation import Conversation, ConversationIntent
        from app.services.campaign_engine import CampaignEngine
        from app.services.conversation_intelligence import ConversationIntelligenceService
        from sqlalchemy import select

        db = await _get_db_session()
        rate_guard = await _get_rate_guard()
        async with db:
            engine = CampaignEngine(db, rate_guard)
            result = await engine.process_reply(lead_id, reply_content)

            if result.get("status") != "processed":
                return result

            intent = result.get("intent")
            next_action = result.get("next_action")

            # Auto-dispatch based on intent
            if intent == "meeting_ready":
                # Notify user via WebSocket (handled at API layer)
                pass
            elif intent == "objection":
                # Get conversation and auto-handle
                lead_result = await db.execute(
                    select(Lead).where(Lead.id == uuid.UUID(lead_id))
                )
                lead = lead_result.scalar_one_or_none()
                if lead:
                    conv_result = await db.execute(
                        select(Conversation)
                        .where(Conversation.lead_id == lead.id)
                        .order_by(Conversation.created_at.desc())
                    )
                    conv = conv_result.scalar_one_or_none()
                    if conv:
                        # Schedule objection handling follow-up
                        send_followup_message.apply_async(
                            args=[str(conv.id), lead_id],
                            countdown=3600,  # 1 hour delay
                        )
            elif next_action == "schedule_followup":
                lead_result = await db.execute(
                    select(Lead).where(Lead.id == uuid.UUID(lead_id))
                )
                lead = lead_result.scalar_one_or_none()
                if lead:
                    conv_result = await db.execute(
                        select(Conversation)
                        .where(Conversation.lead_id == lead.id)
                        .order_by(Conversation.created_at.desc())
                    )
                    conv = conv_result.scalar_one_or_none()
                    if conv:
                        send_followup_message.apply_async(
                            args=[str(conv.id), lead_id],
                            countdown=172800,  # 48 hours
                        )

            await db.commit()
            return result

    return _run_async(_run())
