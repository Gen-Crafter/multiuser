"""Campaign schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    campaign_type: str  # post_generator | connection_growth | sales_outreach
    linkedin_account_id: uuid.UUID

    # Post generator
    topic: Optional[str] = None
    tone: Optional[str] = None
    target_audience: Optional[str] = None
    hashtag_strategy: Optional[dict[str, Any]] = None
    posting_schedule: Optional[dict[str, Any]] = None

    # Connection growth
    icp_description: Optional[str] = None
    target_industry: Optional[str] = None
    target_job_titles: Optional[list[str]] = None
    target_geography: Optional[str] = None
    connection_note_template: Optional[str] = None

    # Sales outreach
    sales_pipeline_config: Optional[dict[str, Any]] = None
    followup_strategy: Optional[dict[str, Any]] = None
    max_followups: int = 5


class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    topic: Optional[str] = None
    tone: Optional[str] = None
    target_audience: Optional[str] = None
    hashtag_strategy: Optional[dict[str, Any]] = None
    posting_schedule: Optional[dict[str, Any]] = None
    icp_description: Optional[str] = None
    target_industry: Optional[str] = None
    target_job_titles: Optional[list[str]] = None
    target_geography: Optional[str] = None
    connection_note_template: Optional[str] = None
    sales_pipeline_config: Optional[dict[str, Any]] = None
    followup_strategy: Optional[dict[str, Any]] = None
    max_followups: Optional[int] = None


class CampaignResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    linkedin_account_id: uuid.UUID
    name: str
    campaign_type: str
    status: str
    topic: Optional[str] = None
    tone: Optional[str] = None
    target_audience: Optional[str] = None
    icp_description: Optional[str] = None
    target_industry: Optional[str] = None
    target_job_titles: Optional[list[str]] = None
    target_geography: Optional[str] = None
    total_leads: int
    total_sent: int
    total_replies: int
    total_meetings: int
    conversion_rate: float
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
