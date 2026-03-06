"""Analytics schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel


class AnalyticsResponse(BaseModel):
    id: uuid.UUID
    linkedin_account_id: uuid.UUID
    date: date
    connections_sent: int
    connections_accepted: int
    messages_sent: int
    messages_received: int
    profile_views: int
    posts_created: int
    post_impressions: int
    post_engagements: int
    connection_acceptance_rate: float
    reply_rate: float
    meeting_rate: float
    risk_score: int
    risk_factors: Optional[dict[str, Any]] = None
    limits_snapshot: Optional[dict[str, Any]] = None

    model_config = {"from_attributes": True}


class CampaignAnalyticsResponse(BaseModel):
    id: uuid.UUID
    campaign_id: uuid.UUID
    date: date
    leads_discovered: int
    invites_sent: int
    connections_made: int
    messages_sent: int
    replies_received: int
    positive_replies: int
    meetings_booked: int
    conversion_rate: float

    model_config = {"from_attributes": True}


class DashboardSummary(BaseModel):
    total_campaigns: int
    active_campaigns: int
    total_leads: int
    total_connections_sent: int
    total_connections_accepted: int
    total_messages_sent: int
    total_replies: int
    total_meetings: int
    overall_connection_rate: float
    overall_reply_rate: float
    overall_meeting_rate: float
    overall_conversion_rate: float
    risk_score: int
    daily_usage: dict[str, Any]
    daily_limits: dict[str, Any]
