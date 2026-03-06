"""Campaign model supporting multiple campaign types."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CampaignType(str, enum.Enum):
    POST_GENERATOR = "post_generator"
    CONNECTION_GROWTH = "connection_growth"
    SALES_OUTREACH = "sales_outreach"


class CampaignStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    linkedin_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("linkedin_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    campaign_type: Mapped[CampaignType] = mapped_column(Enum(CampaignType), nullable=False, index=True)
    status: Mapped[CampaignStatus] = mapped_column(Enum(CampaignStatus), default=CampaignStatus.DRAFT)

    # ── Post Generator config ───────────────────────────
    topic: Mapped[str | None] = mapped_column(Text, nullable=True)
    tone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_audience: Mapped[str | None] = mapped_column(Text, nullable=True)
    hashtag_strategy: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    posting_schedule: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # cron-like

    # ── Connection Growth config ────────────────────────
    icp_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_industry: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_job_titles: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    target_geography: Mapped[str | None] = mapped_column(String(255), nullable=True)
    connection_note_template: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Sales Outreach config ───────────────────────────
    sales_pipeline_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    followup_strategy: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    max_followups: Mapped[int] = mapped_column(Integer, default=5)

    # ── Metrics ─────────────────────────────────────────
    total_leads: Mapped[int] = mapped_column(Integer, default=0)
    total_sent: Mapped[int] = mapped_column(Integer, default=0)
    total_replies: Mapped[int] = mapped_column(Integer, default=0)
    total_meetings: Mapped[int] = mapped_column(Integer, default=0)
    conversion_rate: Mapped[float] = mapped_column(Float, default=0.0)

    # ── LLM performance feedback ────────────────────────
    llm_feedback: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    user = relationship("User", back_populates="campaigns")
    linkedin_account = relationship("LinkedInAccount", back_populates="campaigns")
    leads = relationship("Lead", back_populates="campaign", cascade="all, delete-orphan")
