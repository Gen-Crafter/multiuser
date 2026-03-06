"""Conversation model – memory store for each lead interaction."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ConversationIntent(str, enum.Enum):
    UNKNOWN = "unknown"
    INTERESTED = "interested"
    NOT_INTERESTED = "not_interested"
    OBJECTION = "objection"
    NEEDS_FOLLOWUP = "needs_followup"
    MEETING_READY = "meeting_ready"


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # ── AI-maintained memory fields ─────────────────────
    profile_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_interests: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    pain_points: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    objections_raised: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    conversation_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Intent & sentiment ──────────────────────────────
    current_intent: Mapped[ConversationIntent] = mapped_column(
        Enum(ConversationIntent), default=ConversationIntent.UNKNOWN
    )
    sentiment_score: Mapped[float] = mapped_column(Float, default=0.0)
    conversion_probability: Mapped[float] = mapped_column(Float, default=0.0)

    # ── Follow-up tracking ──────────────────────────────
    followup_stage: Mapped[int] = mapped_column(default=0)
    escalation_level: Mapped[int] = mapped_column(default=0)
    last_followup_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_action: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Embedding vector ID for RAG ─────────────────────
    vector_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    lead = relationship("Lead", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
