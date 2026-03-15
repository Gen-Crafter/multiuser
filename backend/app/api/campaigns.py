"""Campaign CRUD and control endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.campaign import Campaign, CampaignStatus, CampaignType
from app.models.user import User
from app.schemas.campaign import CampaignCreate, CampaignResponse, CampaignUpdate

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.get("/", response_model=list[CampaignResponse])
async def list_campaigns(
    campaign_type: str | None = None,
    status_filter: str | None = None,
    skip: int = 0,
    limit: int = 50,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Campaign).where(Campaign.user_id == user.id)
    if campaign_type:
        query = query.where(Campaign.campaign_type == CampaignType(campaign_type))
    if status_filter:
        query = query.where(Campaign.status == CampaignStatus(status_filter))
    query = query.offset(skip).limit(limit).order_by(Campaign.created_at.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    body: CampaignCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    campaign = Campaign(
        user_id=user.id,
        linkedin_account_id=body.linkedin_account_id,
        name=body.name,
        campaign_type=CampaignType(body.campaign_type),
        topic=body.topic,
        tone=body.tone,
        target_audience=body.target_audience,
        hashtag_strategy=body.hashtag_strategy,
        posting_schedule=body.posting_schedule,
        icp_description=body.icp_description,
        target_industry=body.target_industry,
        target_job_titles=body.target_job_titles,
        target_geography=body.target_geography,
        connection_note_template=body.connection_note_template,
        sales_pipeline_config=body.sales_pipeline_config,
        followup_strategy=body.followup_strategy,
        max_followups=body.max_followups,
    )
    db.add(campaign)
    await db.flush()
    await db.refresh(campaign)
    return campaign


@router.get("/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(
    campaign_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.user_id == user.id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    return campaign


@router.patch("/{campaign_id}", response_model=CampaignResponse)
async def update_campaign(
    campaign_id: uuid.UUID,
    body: CampaignUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.user_id == user.id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    update_data = body.model_dump(exclude_unset=True)
    if "status" in update_data:
        update_data["status"] = CampaignStatus(update_data["status"])
    for field, value in update_data.items():
        setattr(campaign, field, value)

    db.add(campaign)
    await db.flush()
    await db.refresh(campaign)
    return campaign


@router.post("/{campaign_id}/start", response_model=CampaignResponse)
async def start_campaign(
    campaign_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.user_id == user.id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    campaign.status = CampaignStatus.ACTIVE
    db.add(campaign)
    await db.flush()

    # Dispatch appropriate Celery task based on campaign type
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"About to dispatch task for campaign {campaign.id}, type: {campaign.campaign_type}")
    logger.info(f"CampaignType.POST_GENERATOR value: {CampaignType.POST_GENERATOR}")
    logger.info(f"Comparison result: {campaign.campaign_type == CampaignType.POST_GENERATOR}")
    
    logger.info(f"Dispatching task for campaign {campaign.id}, type: {campaign.campaign_type}")
    
    if campaign.campaign_type == CampaignType.POST_GENERATOR:
        from app.tasks.posting_tasks import run_posting_campaign
        logger.info(f"Dispatching run_posting_campaign for {campaign.id}")
        task = run_posting_campaign.delay(str(campaign.id))
        logger.info(f"Task dispatched with ID: {task.id}")
    elif campaign.campaign_type == CampaignType.CONNECTION_GROWTH:
        from app.tasks.connection_tasks import run_connection_campaign
        logger.info(f"Dispatching run_connection_campaign for {campaign.id}")
        run_connection_campaign.delay(str(campaign.id))
    elif campaign.campaign_type == CampaignType.SALES_OUTREACH:
        from app.tasks.sales_tasks import run_sales_campaign
        logger.info(f"Dispatching run_sales_campaign for {campaign.id}")
        run_sales_campaign.delay(str(campaign.id))

    await db.refresh(campaign)
    return campaign


@router.post("/{campaign_id}/pause", response_model=CampaignResponse)
async def pause_campaign(
    campaign_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.user_id == user.id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    campaign.status = CampaignStatus.PAUSED
    db.add(campaign)
    await db.flush()
    await db.refresh(campaign)
    return campaign


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign(
    campaign_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.user_id == user.id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    await db.delete(campaign)
    await db.flush()
