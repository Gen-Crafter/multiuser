"""Lead management endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.campaign import Campaign
from app.models.lead import Lead, LeadStatus
from app.models.user import User
from app.schemas.lead import LeadCreate, LeadDetailResponse, LeadResponse, LeadUpdate

router = APIRouter(prefix="/leads", tags=["leads"])


@router.get("/", response_model=list[LeadResponse])
async def list_leads(
    campaign_id: uuid.UUID | None = None,
    status_filter: str | None = None,
    skip: int = 0,
    limit: int = 50,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Only return leads from user's campaigns
    user_campaign_ids = select(Campaign.id).where(Campaign.user_id == user.id)
    query = select(Lead).where(Lead.campaign_id.in_(user_campaign_ids))

    if campaign_id:
        query = query.where(Lead.campaign_id == campaign_id)
    if status_filter:
        query = query.where(Lead.status == LeadStatus(status_filter))

    query = query.offset(skip).limit(limit).order_by(Lead.created_at.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{lead_id}", response_model=LeadDetailResponse)
async def get_lead(
    lead_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_campaign_ids = select(Campaign.id).where(Campaign.user_id == user.id)
    result = await db.execute(
        select(Lead).where(Lead.id == lead_id, Lead.campaign_id.in_(user_campaign_ids))
    )
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    return lead


@router.patch("/{lead_id}", response_model=LeadResponse)
async def update_lead(
    lead_id: uuid.UUID,
    body: LeadUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_campaign_ids = select(Campaign.id).where(Campaign.user_id == user.id)
    result = await db.execute(
        select(Lead).where(Lead.id == lead_id, Lead.campaign_id.in_(user_campaign_ids))
    )
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")

    update_data = body.model_dump(exclude_unset=True)
    if "status" in update_data:
        update_data["status"] = LeadStatus(update_data["status"])
    for field, value in update_data.items():
        setattr(lead, field, value)

    db.add(lead)
    await db.flush()
    await db.refresh(lead)
    return lead


@router.delete("/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lead(
    lead_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_campaign_ids = select(Campaign.id).where(Campaign.user_id == user.id)
    result = await db.execute(
        select(Lead).where(Lead.id == lead_id, Lead.campaign_id.in_(user_campaign_ids))
    )
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    await db.delete(lead)
    await db.flush()
