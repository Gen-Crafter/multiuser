"""Conversation Intelligence Engine – intent detection, follow-up logic, memory store."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation, ConversationIntent
from app.models.lead import Lead, LeadStatus
from app.models.message import Message, MessageDirection, MessageType
from app.services.llm_service import llm_service


# ── Follow-up escalation ladder ─────────────────────────────
FOLLOWUP_SCHEDULE = [
    {"delay_hours": 48, "strategy": "value_add", "description": "Share relevant insight or resource"},
    {"delay_hours": 96, "strategy": "social_proof", "description": "Mention similar companies/roles"},
    {"delay_hours": 168, "strategy": "direct_ask", "description": "Directly ask about interest"},
    {"delay_hours": 336, "strategy": "breakup", "description": "Final gentle check-in"},
    {"delay_hours": 720, "strategy": "reconnect", "description": "Reconnect with new angle"},
]


class ConversationIntelligenceService:
    """Manages conversation memory, intent detection, and follow-up orchestration."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Intent Detection ────────────────────────────────
    async def detect_and_update_intent(self, conversation_id: str, new_message: str) -> dict[str, Any]:
        conv = await self._get_conversation(conversation_id)
        if not conv:
            return {"error": "conversation not found"}

        # Build history
        history = await self._get_message_history(conv.id)

        # LLM intent detection
        intent_result = await llm_service.detect_intent(new_message, history)

        # Update conversation
        intent_str = intent_result.get("intent", "needs_followup")
        conv.current_intent = ConversationIntent(intent_str)
        conv.sentiment_score = intent_result.get("sentiment", 0.0)
        conv.conversion_probability = intent_result.get("probability", 0.0)
        conv.next_action = self._get_next_action(intent_str, conv.followup_stage)

        # Update memory fields
        if intent_str == "objection":
            objections = conv.objections_raised or []
            objections.append(new_message)
            conv.objections_raised = objections

        self.db.add(conv)
        await self.db.flush()

        return {
            "intent": intent_str,
            "sentiment": conv.sentiment_score,
            "probability": conv.conversion_probability,
            "next_action": conv.next_action,
            "followup_stage": conv.followup_stage,
        }

    # ── Dynamic Follow-up Logic ─────────────────────────
    async def get_followup_candidates(self) -> list[dict]:
        """Find all conversations that need a follow-up now."""
        now = datetime.now(timezone.utc)

        result = await self.db.execute(
            select(Conversation).where(
                Conversation.current_intent.in_([
                    ConversationIntent.UNKNOWN,
                    ConversationIntent.NEEDS_FOLLOWUP,
                ]),
                Conversation.next_action.isnot(None),
            )
        )
        conversations = result.scalars().all()

        candidates = []
        for conv in conversations:
            # Check if enough time has passed since last follow-up
            schedule = FOLLOWUP_SCHEDULE[min(conv.followup_stage, len(FOLLOWUP_SCHEDULE) - 1)]
            delay = timedelta(hours=schedule["delay_hours"])

            last_time = conv.last_followup_at or conv.created_at
            if now >= last_time + delay:
                candidates.append({
                    "conversation_id": str(conv.id),
                    "lead_id": str(conv.lead_id),
                    "followup_stage": conv.followup_stage,
                    "strategy": schedule["strategy"],
                    "description": schedule["description"],
                    "last_followup_at": last_time.isoformat() if last_time else None,
                })

        return candidates

    async def generate_followup_message(self, conversation_id: str) -> dict[str, Any]:
        """Generate and record a follow-up message for a conversation."""
        conv = await self._get_conversation(conversation_id)
        if not conv:
            return {"error": "conversation not found"}

        # Get lead profile
        lead_result = await self.db.execute(select(Lead).where(Lead.id == conv.lead_id))
        lead = lead_result.scalar_one_or_none()
        if not lead:
            return {"error": "lead not found"}

        # Get conversation history
        history = await self._get_message_history(conv.id)

        # Build memory context
        memory = {
            "profile_summary": conv.profile_summary,
            "key_interests": conv.key_interests,
            "pain_points": conv.pain_points,
            "objections": conv.objections_raised,
            "sentiment": conv.sentiment_score,
            "conversion_probability": conv.conversion_probability,
            "conversation_summary": conv.conversation_summary,
        }

        profile_data = lead.scraped_data or {
            "name": lead.linkedin_name,
            "headline": lead.headline,
            "company": lead.company,
            "job_title": lead.job_title,
        }

        # Handle objection vs regular follow-up
        if conv.current_intent == ConversationIntent.OBJECTION and conv.objections_raised:
            last_objection = conv.objections_raised[-1]
            content = await llm_service.handle_objection(last_objection, history, profile_data)
            msg_type = MessageType.OBJECTION_HANDLE
        else:
            content = await llm_service.generate_followup(
                conversation_history=history,
                profile_data=profile_data,
                followup_number=conv.followup_stage + 1,
                conversation_memory=memory,
            )
            msg_type = MessageType.FOLLOWUP

        # Record message
        message = Message(
            lead_id=lead.id,
            conversation_id=conv.id,
            direction=MessageDirection.OUTBOUND,
            message_type=msg_type,
            content=content,
            llm_model_used=llm_service.model,
        )
        self.db.add(message)

        # Update conversation state
        conv.followup_stage += 1
        conv.last_followup_at = datetime.now(timezone.utc)
        conv.escalation_level = min(conv.escalation_level + 1, len(FOLLOWUP_SCHEDULE) - 1)

        # Update lead
        lead.followup_count += 1
        next_schedule = FOLLOWUP_SCHEDULE[min(conv.followup_stage, len(FOLLOWUP_SCHEDULE) - 1)]
        lead.next_followup_at = datetime.now(timezone.utc) + timedelta(hours=next_schedule["delay_hours"])

        # Re-summarize conversation
        updated_history = history + [{"role": "assistant", "content": content}]
        conv.conversation_summary = await llm_service.summarize_conversation(updated_history)

        # Store in vector DB
        await llm_service.store_embedding(
            f"Follow-up #{conv.followup_stage} to {lead.linkedin_name}: {content}",
            metadata={"lead_id": str(lead.id), "type": "followup"},
        )

        self.db.add(conv)
        self.db.add(lead)
        await self.db.flush()

        return {
            "status": "generated",
            "content": content,
            "message_type": msg_type.value,
            "followup_stage": conv.followup_stage,
            "lead_id": str(lead.id),
        }

    # ── Memory Store Operations ─────────────────────────
    async def update_memory(self, conversation_id: str, updates: dict[str, Any]) -> dict:
        conv = await self._get_conversation(conversation_id)
        if not conv:
            return {"error": "conversation not found"}

        for field in ["profile_summary", "key_interests", "pain_points", "objections_raised", "conversation_summary"]:
            if field in updates:
                setattr(conv, field, updates[field])

        self.db.add(conv)
        await self.db.flush()
        return {"status": "updated"}

    async def get_memory(self, conversation_id: str) -> dict[str, Any]:
        conv = await self._get_conversation(conversation_id)
        if not conv:
            return {"error": "conversation not found"}

        return {
            "conversation_id": str(conv.id),
            "lead_id": str(conv.lead_id),
            "profile_summary": conv.profile_summary,
            "key_interests": conv.key_interests,
            "pain_points": conv.pain_points,
            "objections_raised": conv.objections_raised,
            "conversation_summary": conv.conversation_summary,
            "current_intent": conv.current_intent.value,
            "sentiment_score": conv.sentiment_score,
            "conversion_probability": conv.conversion_probability,
            "followup_stage": conv.followup_stage,
            "escalation_level": conv.escalation_level,
        }

    # ── Helpers ─────────────────────────────────────────
    async def _get_conversation(self, conversation_id: str) -> Conversation | None:
        result = await self.db.execute(
            select(Conversation).where(Conversation.id == uuid.UUID(conversation_id))
        )
        return result.scalar_one_or_none()

    async def _get_message_history(self, conversation_id: uuid.UUID) -> list[dict]:
        result = await self.db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
        )
        messages = result.scalars().all()
        return [
            {"role": "assistant" if m.direction == MessageDirection.OUTBOUND else "user", "content": m.content}
            for m in messages
        ]

    @staticmethod
    def _get_next_action(intent: str, followup_stage: int) -> str:
        if intent == "interested":
            return "propose_meeting"
        elif intent == "meeting_ready":
            return "send_calendar_link"
        elif intent == "not_interested":
            return "close_conversation"
        elif intent == "objection":
            return "handle_objection"
        else:
            if followup_stage >= len(FOLLOWUP_SCHEDULE):
                return "close_conversation"
            return f"followup_stage_{followup_stage + 1}"
