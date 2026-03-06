"""Lead model for tracking discovered LinkedIn profiles."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class LeadStatus(str, enum.Enum):
    DISCOVERED = "discovered"
    PROFILE_SCRAPED = "profile_scraped"
    INVITE_SENT = "invite_sent"
    CONNECTED = "connected"
    MESSAGE_SENT = "message_sent"
    REPLIED = "replied"
    INTERESTED = "interested"
    NOT_INTERESTED = "not_interested"
    MEETING_BOOKED = "meeting_booked"
    CONVERTED = "converted"
    OBJECTION = "objection"
    DO_NOT_CONTACT = "do_not_contact"


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    linkedin_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("linkedin_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # ── Profile data ────────────────────────────────────
    linkedin_url: Mapped[str] = mapped_column(Text, nullable=False)
    linkedin_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    headline: Mapped[str | None] = mapped_column(Text, nullable=True)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(255), nullable=True)
    profile_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    scraped_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # ── Status & pipeline ───────────────────────────────
    status: Mapped[LeadStatus] = mapped_column(Enum(LeadStatus), default=LeadStatus.DISCOVERED, index=True)
    followup_count: Mapped[int] = mapped_column(Integer, default=0)
    next_followup_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── AI analysis ─────────────────────────────────────
    llm_profile_analysis: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    key_interests: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    pain_points: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    objections_raised: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    sentiment_score: Mapped[float] = mapped_column(Float, default=0.0)
    conversion_probability: Mapped[float] = mapped_column(Float, default=0.0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    campaign = relationship("Campaign", back_populates="leads")
    linkedin_account = relationship("LinkedInAccount", back_populates="leads")
    conversations = relationship("Conversation", back_populates="lead", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="lead", cascade="all, delete-orphan")
