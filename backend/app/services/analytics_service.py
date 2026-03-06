"""Analytics service – aggregation, risk computation, and feedback loops."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics import Analytics, CampaignAnalytics
from app.models.campaign import Campaign
from app.models.lead import Lead, LeadStatus
from app.models.linkedin_account import LinkedInAccount
from app.services.rate_guard import RateGuardService


class AnalyticsService:
    """Computes and stores daily analytics snapshots."""

    def __init__(self, db: AsyncSession, rate_guard: RateGuardService):
        self.db = db
        self.rate_guard = rate_guard

    async def snapshot_daily_analytics(self, account_id: str) -> Analytics:
        """Create or update today's analytics row for a LinkedIn account."""
        today = date.today()
        uid = uuid.UUID(account_id)

        result = await self.db.execute(
            select(Analytics).where(Analytics.linkedin_account_id == uid, Analytics.date == today)
        )
        analytics = result.scalar_one_or_none()
        if not analytics:
            analytics = Analytics(linkedin_account_id=uid, date=today)

        # Pull current counters from Redis rate guard
        usage = await self.rate_guard.get_usage(account_id)
        analytics.connections_sent = usage.get("connection_request", 0)
        analytics.messages_sent = usage.get("message", 0)
        analytics.profile_views = usage.get("profile_view", 0)
        analytics.posts_created = usage.get("post", 0)

        # Compute acceptance rate from leads table
        account_campaigns = select(Campaign.id).where(Campaign.linkedin_account_id == uid)
        total_invites = await self.db.execute(
            select(func.count(Lead.id)).where(
                Lead.campaign_id.in_(account_campaigns),
                Lead.status != LeadStatus.DISCOVERED,
            )
        )
        total_connected = await self.db.execute(
            select(func.count(Lead.id)).where(
                Lead.campaign_id.in_(account_campaigns),
                Lead.status.in_([
                    LeadStatus.CONNECTED, LeadStatus.MESSAGE_SENT, LeadStatus.REPLIED,
                    LeadStatus.INTERESTED, LeadStatus.MEETING_BOOKED, LeadStatus.CONVERTED,
                ]),
            )
        )
        inv_count = total_invites.scalar() or 0
        conn_count = total_connected.scalar() or 0
        analytics.connections_accepted = conn_count
        analytics.connection_acceptance_rate = round(conn_count / max(inv_count, 1) * 100, 2)

        # Risk score
        risk = await self.rate_guard.compute_risk(account_id)
        analytics.risk_score = risk

        # Get account type for limits
        acct_result = await self.db.execute(select(LinkedInAccount).where(LinkedInAccount.id == uid))
        account = acct_result.scalar_one_or_none()
        if account:
            analytics.limits_snapshot = await self.rate_guard.get_limits_snapshot(
                account_id, account.account_type.value, account.warmup_day
            )

        self.db.add(analytics)
        await self.db.flush()
        return analytics

    async def snapshot_campaign_analytics(self, campaign_id: str) -> CampaignAnalytics:
        """Create or update today's campaign analytics row."""
        today = date.today()
        cid = uuid.UUID(campaign_id)

        result = await self.db.execute(
            select(CampaignAnalytics).where(CampaignAnalytics.campaign_id == cid, CampaignAnalytics.date == today)
        )
        ca = result.scalar_one_or_none()
        if not ca:
            ca = CampaignAnalytics(campaign_id=cid, date=today)

        # Count leads by status
        base = select(Lead).where(Lead.campaign_id == cid)

        discovered = await self.db.execute(select(func.count(Lead.id)).where(Lead.campaign_id == cid))
        ca.leads_discovered = discovered.scalar() or 0

        invited = await self.db.execute(
            select(func.count(Lead.id)).where(Lead.campaign_id == cid, Lead.status != LeadStatus.DISCOVERED)
        )
        ca.invites_sent = invited.scalar() or 0

        connected = await self.db.execute(
            select(func.count(Lead.id)).where(
                Lead.campaign_id == cid,
                Lead.status.in_([
                    LeadStatus.CONNECTED, LeadStatus.MESSAGE_SENT, LeadStatus.REPLIED,
                    LeadStatus.INTERESTED, LeadStatus.MEETING_BOOKED, LeadStatus.CONVERTED,
                ]),
            )
        )
        ca.connections_made = connected.scalar() or 0

        replied = await self.db.execute(
            select(func.count(Lead.id)).where(
                Lead.campaign_id == cid,
                Lead.status.in_([LeadStatus.REPLIED, LeadStatus.INTERESTED, LeadStatus.MEETING_BOOKED, LeadStatus.CONVERTED]),
            )
        )
        ca.replies_received = replied.scalar() or 0

        meetings = await self.db.execute(
            select(func.count(Lead.id)).where(
                Lead.campaign_id == cid,
                Lead.status.in_([LeadStatus.MEETING_BOOKED, LeadStatus.CONVERTED]),
            )
        )
        ca.meetings_booked = meetings.scalar() or 0

        ca.conversion_rate = round(ca.meetings_booked / max(ca.leads_discovered, 1) * 100, 2)

        self.db.add(ca)
        await self.db.flush()
        return ca

    async def compute_llm_feedback(self, campaign_id: str) -> dict[str, Any]:
        """Compute message performance feedback for LLM learning loop."""
        cid = uuid.UUID(campaign_id)

        campaign_result = await self.db.execute(select(Campaign).where(Campaign.id == cid))
        campaign = campaign_result.scalar_one_or_none()
        if not campaign:
            return {}

        total = max(campaign.total_sent, 1)
        feedback = {
            "total_sent": campaign.total_sent,
            "total_replies": campaign.total_replies,
            "total_meetings": campaign.total_meetings,
            "reply_rate": round(campaign.total_replies / total * 100, 2),
            "meeting_rate": round(campaign.total_meetings / max(campaign.total_replies, 1) * 100, 2),
            "conversion_rate": round(campaign.total_meetings / total * 100, 2),
            "recommendation": self._generate_recommendation(
                campaign.total_replies / total,
                campaign.total_meetings / max(campaign.total_replies, 1),
            ),
        }

        campaign.llm_feedback = feedback
        campaign.conversion_rate = feedback["conversion_rate"]
        self.db.add(campaign)
        await self.db.flush()

        return feedback

    @staticmethod
    def _generate_recommendation(reply_rate: float, meeting_rate: float) -> str:
        tips = []
        if reply_rate < 0.1:
            tips.append("Reply rate is low. Try more personalized opening lines referencing specific profile details.")
        elif reply_rate < 0.2:
            tips.append("Reply rate is moderate. Experiment with different value propositions in the first message.")

        if meeting_rate < 0.1:
            tips.append("Meeting conversion is low. Include a clearer call-to-action and specific time slots.")
        elif meeting_rate < 0.3:
            tips.append("Meeting conversion is moderate. Try addressing common objections preemptively.")

        if not tips:
            tips.append("Performance is strong. Continue current strategy and A/B test minor variations.")

        return " ".join(tips)
