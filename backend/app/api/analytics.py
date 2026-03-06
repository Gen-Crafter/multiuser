"""Analytics endpoints – dashboard summary, daily metrics, campaign metrics."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.analytics import Analytics, CampaignAnalytics
from app.models.campaign import Campaign, CampaignStatus
from app.models.lead import Lead
from app.models.linkedin_account import LinkedInAccount
from app.models.user import User
from app.schemas.analytics import AnalyticsResponse, CampaignAnalyticsResponse, DashboardSummary

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/dashboard", response_model=DashboardSummary)
async def get_dashboard(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Campaign counts
    total_q = await db.execute(select(func.count(Campaign.id)).where(Campaign.user_id == user.id))
    total_campaigns = total_q.scalar() or 0

    active_q = await db.execute(
        select(func.count(Campaign.id)).where(Campaign.user_id == user.id, Campaign.status == CampaignStatus.ACTIVE)
    )
    active_campaigns = active_q.scalar() or 0

    # Aggregate lead counts
    user_campaign_ids = select(Campaign.id).where(Campaign.user_id == user.id)
    lead_q = await db.execute(select(func.count(Lead.id)).where(Lead.campaign_id.in_(user_campaign_ids)))
    total_leads = lead_q.scalar() or 0

    # Aggregate campaign metrics
    metrics_q = await db.execute(
        select(
            func.coalesce(func.sum(Campaign.total_sent), 0),
            func.coalesce(func.sum(Campaign.total_replies), 0),
            func.coalesce(func.sum(Campaign.total_meetings), 0),
        ).where(Campaign.user_id == user.id)
    )
    row = metrics_q.one()
    total_sent = row[0]
    total_replies = row[1]
    total_meetings = row[2]

    # Today's analytics across all accounts
    today = date.today()
    account_ids = select(LinkedInAccount.id).where(LinkedInAccount.user_id == user.id)
    daily_q = await db.execute(
        select(
            func.coalesce(func.sum(Analytics.connections_sent), 0),
            func.coalesce(func.sum(Analytics.connections_accepted), 0),
            func.coalesce(func.sum(Analytics.messages_sent), 0),
            func.coalesce(func.max(Analytics.risk_score), 0),
        ).where(Analytics.linkedin_account_id.in_(account_ids), Analytics.date == today)
    )
    d = daily_q.one()

    conn_sent = d[0]
    conn_accepted = d[1]
    msgs_sent = d[2]
    risk = d[3]

    return DashboardSummary(
        total_campaigns=total_campaigns,
        active_campaigns=active_campaigns,
        total_leads=total_leads,
        total_connections_sent=conn_sent,
        total_connections_accepted=conn_accepted,
        total_messages_sent=total_sent,
        total_replies=total_replies,
        total_meetings=total_meetings,
        overall_connection_rate=round(conn_accepted / max(conn_sent, 1) * 100, 2),
        overall_reply_rate=round(total_replies / max(total_sent, 1) * 100, 2),
        overall_meeting_rate=round(total_meetings / max(total_replies, 1) * 100, 2),
        overall_conversion_rate=round(total_meetings / max(total_leads, 1) * 100, 2),
        risk_score=risk,
        daily_usage={
            "connections_sent": conn_sent,
            "messages_sent": msgs_sent,
        },
        daily_limits={
            "connections": 25,
            "messages": 50,
        },
    )


@router.get("/daily", response_model=list[AnalyticsResponse])
async def get_daily_analytics(
    linkedin_account_id: uuid.UUID,
    days: int = Query(default=30, le=90),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    start_date = date.today() - timedelta(days=days)
    result = await db.execute(
        select(Analytics)
        .where(
            Analytics.linkedin_account_id == linkedin_account_id,
            Analytics.date >= start_date,
        )
        .order_by(Analytics.date.desc())
    )
    return result.scalars().all()


@router.get("/campaign/{campaign_id}", response_model=list[CampaignAnalyticsResponse])
async def get_campaign_analytics(
    campaign_id: uuid.UUID,
    days: int = Query(default=30, le=90),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    start_date = date.today() - timedelta(days=days)
    result = await db.execute(
        select(CampaignAnalytics)
        .where(
            CampaignAnalytics.campaign_id == campaign_id,
            CampaignAnalytics.date >= start_date,
        )
        .order_by(CampaignAnalytics.date.desc())
    )
    return result.scalars().all()
