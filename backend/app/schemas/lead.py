"""Lead schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class LeadCreate(BaseModel):
    campaign_id: uuid.UUID
    linkedin_account_id: uuid.UUID
    linkedin_url: str
    linkedin_name: Optional[str] = None
    headline: Optional[str] = None
    company: Optional[str] = None
    job_title: Optional[str] = None
    location: Optional[str] = None
    industry: Optional[str] = None


class LeadUpdate(BaseModel):
    status: Optional[str] = None
    linkedin_name: Optional[str] = None
    headline: Optional[str] = None
    company: Optional[str] = None
    job_title: Optional[str] = None
    location: Optional[str] = None
    profile_summary: Optional[str] = None
    scraped_data: Optional[dict[str, Any]] = None
    llm_profile_analysis: Optional[dict[str, Any]] = None
    key_interests: Optional[list[str]] = None
    pain_points: Optional[list[str]] = None
    sentiment_score: Optional[float] = None
    conversion_probability: Optional[float] = None


class LeadResponse(BaseModel):
    id: uuid.UUID
    campaign_id: uuid.UUID
    linkedin_account_id: uuid.UUID
    linkedin_url: str
    linkedin_name: Optional[str] = None
    headline: Optional[str] = None
    company: Optional[str] = None
    job_title: Optional[str] = None
    location: Optional[str] = None
    industry: Optional[str] = None
    status: str
    followup_count: int
    next_followup_at: Optional[datetime] = None
    sentiment_score: float
    conversion_probability: float
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LeadDetailResponse(LeadResponse):
    profile_summary: Optional[str] = None
    scraped_data: Optional[dict[str, Any]] = None
    llm_profile_analysis: Optional[dict[str, Any]] = None
    key_interests: Optional[list[str]] = None
    pain_points: Optional[list[str]] = None
    objections_raised: Optional[list[str]] = None
