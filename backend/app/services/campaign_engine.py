"""Campaign engine – orchestrates campaign execution across all types."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign, CampaignStatus, CampaignType
from app.models.lead import Lead, LeadStatus
from app.models.message import Message, MessageDirection, MessageType
from app.models.conversation import Conversation, ConversationIntent
from app.services.llm_service import llm_service
from app.services.rate_guard import RateGuardService, RateAction


class CampaignEngine:
    """Core orchestrator for all campaign types."""

    def __init__(self, db: AsyncSession, rate_guard: RateGuardService):
        self.db = db
        self.rate_guard = rate_guard

    # ── Post Generator Campaign ─────────────────────────
    async def execute_post_campaign(self, campaign_id: str) -> dict[str, Any]:
        campaign = await self._get_campaign(campaign_id)
        if not campaign or campaign.status != CampaignStatus.ACTIVE:
            return {"status": "skipped", "reason": "campaign not active"}

        account_id = str(campaign.linkedin_account_id)

        # Rate check
        allowed, info = await self.rate_guard.can_perform(
            account_id, RateAction.POST, campaign_type_to_account_type(campaign)
        )
        if not allowed:
            return {"status": "rate_limited", **info}

        # Get previous post performance for feedback loop
        previous_performance = campaign.llm_feedback or {}

        # Generate post via LLM
        post_content = await llm_service.generate_post(
            topic=campaign.topic or "industry insights",
            tone=campaign.tone or "professional",
            audience=campaign.target_audience or "professionals",
            previous_performance=previous_performance,
            hashtags=campaign.hashtag_strategy.get("hashtags", []) if campaign.hashtag_strategy else None,
        )

        await self.rate_guard.record_action(account_id, RateAction.POST)

        return {
            "status": "generated",
            "content": post_content,
            "campaign_id": campaign_id,
            "account_id": account_id,
        }

    # ── Connection Growth Campaign ──────────────────────
    async def execute_connection_campaign(self, campaign_id: str, leads: list[dict]) -> dict[str, Any]:
        campaign = await self._get_campaign(campaign_id)
        if not campaign or campaign.status != CampaignStatus.ACTIVE:
            return {"status": "skipped", "reason": "campaign not active"}

        account_id = str(campaign.linkedin_account_id)
        results = {"sent": 0, "skipped": 0, "errors": 0, "details": []}

        for lead_data in leads:
            # Rate check
            allowed, info = await self.rate_guard.can_perform(
                account_id, RateAction.CONNECTION_REQUEST
            )
            if not allowed:
                results["skipped"] += len(leads) - results["sent"] - results["errors"]
                results["rate_limit_info"] = info
                break

            try:
                # Generate personalized connection note
                note = await llm_service.generate_connection_note(lead_data)

                # Create or update lead record
                lead = await self._upsert_lead(campaign, lead_data)

                # Record the invite message
                message = Message(
                    lead_id=lead.id,
                    direction=MessageDirection.OUTBOUND,
                    message_type=MessageType.CONNECTION_NOTE,
                    content=note,
                    llm_model_used=llm_service.model,
                )
                self.db.add(message)

                lead.status = LeadStatus.INVITE_SENT
                self.db.add(lead)

                await self.rate_guard.record_action(account_id, RateAction.CONNECTION_REQUEST)
                results["sent"] += 1
                results["details"].append({
                    "lead_url": lead_data.get("linkedin_url"),
                    "note": note,
                    "status": "sent",
                })

            except Exception as e:
                results["errors"] += 1
                results["details"].append({
                    "lead_url": lead_data.get("linkedin_url"),
                    "error": str(e),
                })

        # Update campaign metrics
        campaign.total_sent += results["sent"]
        campaign.total_leads += results["sent"]
        self.db.add(campaign)
        await self.db.flush()

        return results

    # ── Sales Outreach Campaign ─────────────────────────
    async def execute_sales_outreach(self, campaign_id: str, lead_id: str) -> dict[str, Any]:
        campaign = await self._get_campaign(campaign_id)
        if not campaign or campaign.status != CampaignStatus.ACTIVE:
            return {"status": "skipped", "reason": "campaign not active"}

        account_id = str(campaign.linkedin_account_id)

        # Rate check
        allowed, info = await self.rate_guard.can_perform(account_id, RateAction.MESSAGE)
        if not allowed:
            return {"status": "rate_limited", **info}

        # Get lead
        result = await self.db.execute(select(Lead).where(Lead.id == uuid.UUID(lead_id)))
        lead = result.scalar_one_or_none()
        if not lead:
            return {"status": "error", "reason": "lead not found"}

        # Analyze profile if not done
        if not lead.llm_profile_analysis:
            profile_data = lead.scraped_data or {
                "name": lead.linkedin_name,
                "headline": lead.headline,
                "company": lead.company,
                "job_title": lead.job_title,
                "location": lead.location,
            }
            analysis = await llm_service.analyze_profile(profile_data)
            lead.llm_profile_analysis = analysis
            lead.key_interests = analysis.get("key_interests", [])
            lead.pain_points = analysis.get("pain_points", [])

            # Store profile in vector DB for RAG
            await llm_service.store_embedding(
                json.dumps(profile_data),
                metadata={"lead_id": str(lead.id), "campaign_id": campaign_id},
            )

        # Generate first message
        profile_data = lead.scraped_data or {"name": lead.linkedin_name, "headline": lead.headline}
        campaign_context = campaign.icp_description or ""
        first_message = await llm_service.generate_first_message(profile_data, campaign_context)

        # Create conversation
        conversation = Conversation(
            lead_id=lead.id,
            profile_summary=lead.profile_summary,
            key_interests=lead.key_interests,
            pain_points=lead.pain_points,
            current_intent=ConversationIntent.UNKNOWN,
        )
        self.db.add(conversation)
        await self.db.flush()

        # Record message
        message = Message(
            lead_id=lead.id,
            conversation_id=conversation.id,
            direction=MessageDirection.OUTBOUND,
            message_type=MessageType.FIRST_MESSAGE,
            content=first_message,
            llm_model_used=llm_service.model,
        )
        self.db.add(message)

        lead.status = LeadStatus.MESSAGE_SENT
        campaign.total_sent += 1
        self.db.add(lead)
        self.db.add(campaign)

        await self.rate_guard.record_action(account_id, RateAction.MESSAGE)
        await self.db.flush()

        return {
            "status": "sent",
            "lead_id": str(lead.id),
            "conversation_id": str(conversation.id),
            "message": first_message,
        }

    # ── Process inbound reply ───────────────────────────
    async def process_reply(self, lead_id: str, reply_content: str) -> dict[str, Any]:
        result = await self.db.execute(select(Lead).where(Lead.id == uuid.UUID(lead_id)))
        lead = result.scalar_one_or_none()
        if not lead:
            return {"status": "error", "reason": "lead not found"}

        # Get existing conversation
        conv_result = await self.db.execute(
            select(Conversation).where(Conversation.lead_id == lead.id).order_by(Conversation.created_at.desc())
        )
        conversation = conv_result.scalar_one_or_none()
        if not conversation:
            conversation = Conversation(lead_id=lead.id)
            self.db.add(conversation)
            await self.db.flush()

        # Store inbound message
        message = Message(
            lead_id=lead.id,
            conversation_id=conversation.id,
            direction=MessageDirection.INBOUND,
            message_type=MessageType.REPLY,
            content=reply_content,
        )
        self.db.add(message)

        # Get conversation history for intent detection
        msgs_result = await self.db.execute(
            select(Message).where(Message.conversation_id == conversation.id).order_by(Message.created_at)
        )
        messages = msgs_result.scalars().all()
        history = [{"role": "assistant" if m.direction == MessageDirection.OUTBOUND else "user", "content": m.content} for m in messages]

        # Detect intent
        intent_result = await llm_service.detect_intent(reply_content, history)

        # Update conversation
        intent_str = intent_result.get("intent", "needs_followup")
        conversation.current_intent = ConversationIntent(intent_str)
        conversation.sentiment_score = intent_result.get("sentiment", 0.0)
        conversation.conversion_probability = intent_result.get("probability", 0.0)

        # Update lead
        lead.status = LeadStatus(intent_str) if intent_str in [e.value for e in LeadStatus] else LeadStatus.REPLIED
        lead.sentiment_score = conversation.sentiment_score
        lead.conversion_probability = conversation.conversion_probability

        # Summarize conversation
        conversation.conversation_summary = await llm_service.summarize_conversation(history)

        # Store in vector DB
        await llm_service.store_embedding(
            f"Reply from {lead.linkedin_name}: {reply_content}",
            metadata={"lead_id": str(lead.id), "intent": intent_str},
        )

        # Update campaign reply count
        campaign_result = await self.db.execute(select(Campaign).where(Campaign.id == lead.campaign_id))
        campaign = campaign_result.scalar_one_or_none()
        if campaign:
            campaign.total_replies += 1
            if intent_str == "meeting_ready":
                campaign.total_meetings += 1
            self.db.add(campaign)

        self.db.add(conversation)
        self.db.add(lead)
        await self.db.flush()

        return {
            "status": "processed",
            "intent": intent_str,
            "sentiment": conversation.sentiment_score,
            "probability": conversation.conversion_probability,
            "next_action": self._determine_next_action(intent_str),
        }

    # ── Helpers ─────────────────────────────────────────
    async def _get_campaign(self, campaign_id: str) -> Campaign | None:
        result = await self.db.execute(select(Campaign).where(Campaign.id == uuid.UUID(campaign_id)))
        return result.scalar_one_or_none()

    async def _upsert_lead(self, campaign: Campaign, lead_data: dict) -> Lead:
        linkedin_url = lead_data.get("linkedin_url", "")
        result = await self.db.execute(
            select(Lead).where(Lead.campaign_id == campaign.id, Lead.linkedin_url == linkedin_url)
        )
        lead = result.scalar_one_or_none()
        if lead:
            return lead

        lead = Lead(
            campaign_id=campaign.id,
            linkedin_account_id=campaign.linkedin_account_id,
            linkedin_url=linkedin_url,
            linkedin_name=lead_data.get("name"),
            headline=lead_data.get("headline"),
            company=lead_data.get("company"),
            job_title=lead_data.get("job_title"),
            location=lead_data.get("location"),
            industry=lead_data.get("industry"),
        )
        self.db.add(lead)
        await self.db.flush()
        return lead

    @staticmethod
    def _determine_next_action(intent: str) -> str:
        actions = {
            "interested": "send_meeting_proposal",
            "not_interested": "mark_closed",
            "objection": "handle_objection",
            "needs_followup": "schedule_followup",
            "meeting_ready": "send_calendar_link",
        }
        return actions.get(intent, "schedule_followup")


def campaign_type_to_account_type(campaign: Campaign) -> str:
    """Infer account type from campaign's linked account."""
    return "normal"  # Resolved at runtime from LinkedInAccount.account_type
