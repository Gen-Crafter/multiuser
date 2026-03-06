"""Analytics models for tracking platform and campaign metrics."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, date

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Analytics(Base):
    """Daily per-account activity analytics."""

    __tablename__ = "analytics"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    linkedin_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("linkedin_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # Daily counters
    connections_sent: Mapped[int] = mapped_column(Integer, default=0)
    connections_accepted: Mapped[int] = mapped_column(Integer, default=0)
    messages_sent: Mapped[int] = mapped_column(Integer, default=0)
    messages_received: Mapped[int] = mapped_column(Integer, default=0)
    profile_views: Mapped[int] = mapped_column(Integer, default=0)
    posts_created: Mapped[int] = mapped_column(Integer, default=0)
    post_impressions: Mapped[int] = mapped_column(Integer, default=0)
    post_engagements: Mapped[int] = mapped_column(Integer, default=0)

    # Rates
    connection_acceptance_rate: Mapped[float] = mapped_column(Float, default=0.0)
    reply_rate: Mapped[float] = mapped_column(Float, default=0.0)
    meeting_rate: Mapped[float] = mapped_column(Float, default=0.0)

    # Risk
    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    risk_factors: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Limits used vs allowed
    limits_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class CampaignAnalytics(Base):
    """Aggregated campaign-level analytics."""

    __tablename__ = "campaign_analytics"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    leads_discovered: Mapped[int] = mapped_column(Integer, default=0)
    invites_sent: Mapped[int] = mapped_column(Integer, default=0)
    connections_made: Mapped[int] = mapped_column(Integer, default=0)
    messages_sent: Mapped[int] = mapped_column(Integer, default=0)
    replies_received: Mapped[int] = mapped_column(Integer, default=0)
    positive_replies: Mapped[int] = mapped_column(Integer, default=0)
    meetings_booked: Mapped[int] = mapped_column(Integer, default=0)
    conversion_rate: Mapped[float] = mapped_column(Float, default=0.0)

    # LLM feedback for learning
    message_performance: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
