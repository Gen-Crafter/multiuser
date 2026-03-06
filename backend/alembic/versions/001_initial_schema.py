"""Initial schema – all core tables.

Revision ID: 001
Revises: 
Create Date: 2025-01-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), unique=True, nullable=False, index=True),
        sa.Column("hashed_password", sa.Text, nullable=True),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("role", sa.Enum("admin", "manager", "user", name="userrole"), default="user"),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("is_verified", sa.Boolean, default=False),
        sa.Column("google_id", sa.String(255), unique=True, nullable=True),
        sa.Column("avatar_url", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Subscriptions
    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), unique=True),
        sa.Column("tier", sa.Enum("free", "linkedin_normal", "linkedin_premium", name="subscriptiontier"), default="free"),
        sa.Column("status", sa.Enum("active", "cancelled", "expired", "trial", name="subscriptionstatus"), default="trial"),
        sa.Column("features", postgresql.JSONB, nullable=True),
        sa.Column("max_linkedin_accounts", sa.Integer, default=1),
        sa.Column("max_active_campaigns", sa.Integer, default=1),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # LinkedIn Accounts
    op.create_table(
        "linkedin_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), index=True),
        sa.Column("linkedin_email", sa.String(320), nullable=False),
        sa.Column("linkedin_name", sa.String(255), nullable=True),
        sa.Column("linkedin_profile_url", sa.Text, nullable=True),
        sa.Column("account_type", sa.Enum("normal", "premium", name="accounttype"), default="normal"),
        sa.Column("status", sa.Enum("active", "session_expired", "suspended", "cooldown", "warmup", name="accountstatus"), default="session_expired"),
        sa.Column("encrypted_cookies", sa.Text, nullable=True),
        sa.Column("encrypted_password", sa.Text, nullable=True),
        sa.Column("proxy_url", sa.Text, nullable=True),
        sa.Column("fingerprint_config", postgresql.JSONB, nullable=True),
        sa.Column("is_warming_up", sa.Boolean, default=True),
        sa.Column("warmup_day", sa.Integer, default=0),
        sa.Column("risk_score", sa.Integer, default=0),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Campaigns
    op.create_table(
        "campaigns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), index=True),
        sa.Column("linkedin_account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("linkedin_accounts.id", ondelete="CASCADE"), index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("campaign_type", sa.Enum("post_generator", "connection_growth", "sales_outreach", name="campaigntype"), index=True),
        sa.Column("status", sa.Enum("draft", "active", "paused", "completed", "failed", name="campaignstatus"), default="draft"),
        sa.Column("topic", sa.Text, nullable=True),
        sa.Column("tone", sa.String(50), nullable=True),
        sa.Column("target_audience", sa.Text, nullable=True),
        sa.Column("hashtag_strategy", postgresql.JSONB, nullable=True),
        sa.Column("posting_schedule", postgresql.JSONB, nullable=True),
        sa.Column("icp_description", sa.Text, nullable=True),
        sa.Column("target_industry", sa.String(255), nullable=True),
        sa.Column("target_job_titles", postgresql.JSONB, nullable=True),
        sa.Column("target_geography", sa.String(255), nullable=True),
        sa.Column("connection_note_template", sa.Text, nullable=True),
        sa.Column("sales_pipeline_config", postgresql.JSONB, nullable=True),
        sa.Column("followup_strategy", postgresql.JSONB, nullable=True),
        sa.Column("max_followups", sa.Integer, default=5),
        sa.Column("total_leads", sa.Integer, default=0),
        sa.Column("total_sent", sa.Integer, default=0),
        sa.Column("total_replies", sa.Integer, default=0),
        sa.Column("total_meetings", sa.Integer, default=0),
        sa.Column("conversion_rate", sa.Float, default=0.0),
        sa.Column("llm_feedback", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Leads
    op.create_table(
        "leads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), index=True),
        sa.Column("linkedin_account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("linkedin_accounts.id", ondelete="CASCADE"), index=True),
        sa.Column("linkedin_url", sa.Text, nullable=False),
        sa.Column("linkedin_name", sa.String(255), nullable=True),
        sa.Column("headline", sa.Text, nullable=True),
        sa.Column("company", sa.String(255), nullable=True),
        sa.Column("job_title", sa.String(255), nullable=True),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("industry", sa.String(255), nullable=True),
        sa.Column("profile_summary", sa.Text, nullable=True),
        sa.Column("scraped_data", postgresql.JSONB, nullable=True),
        sa.Column("status", sa.Enum(
            "discovered", "profile_scraped", "invite_sent", "connected",
            "message_sent", "replied", "interested", "not_interested",
            "meeting_booked", "converted", "objection", "do_not_contact",
            name="leadstatus"
        ), default="discovered", index=True),
        sa.Column("followup_count", sa.Integer, default=0),
        sa.Column("next_followup_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("llm_profile_analysis", postgresql.JSONB, nullable=True),
        sa.Column("key_interests", postgresql.JSONB, nullable=True),
        sa.Column("pain_points", postgresql.JSONB, nullable=True),
        sa.Column("objections_raised", postgresql.JSONB, nullable=True),
        sa.Column("sentiment_score", sa.Float, default=0.0),
        sa.Column("conversion_probability", sa.Float, default=0.0),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Conversations
    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("leads.id", ondelete="CASCADE"), index=True),
        sa.Column("profile_summary", sa.Text, nullable=True),
        sa.Column("key_interests", postgresql.JSONB, nullable=True),
        sa.Column("pain_points", postgresql.JSONB, nullable=True),
        sa.Column("objections_raised", postgresql.JSONB, nullable=True),
        sa.Column("conversation_summary", sa.Text, nullable=True),
        sa.Column("current_intent", sa.Enum(
            "unknown", "interested", "not_interested", "objection",
            "needs_followup", "meeting_ready", name="conversationintent"
        ), default="unknown"),
        sa.Column("sentiment_score", sa.Float, default=0.0),
        sa.Column("conversion_probability", sa.Float, default=0.0),
        sa.Column("followup_stage", sa.Integer, default=0),
        sa.Column("escalation_level", sa.Integer, default=0),
        sa.Column("last_followup_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_action", sa.Text, nullable=True),
        sa.Column("vector_ids", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Messages
    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("leads.id", ondelete="CASCADE"), index=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("direction", sa.Enum("outbound", "inbound", name="messagedirection")),
        sa.Column("message_type", sa.Enum(
            "connection_note", "first_message", "followup", "reply", "objection_handle",
            name="messagetype"
        )),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("llm_prompt_used", sa.Text, nullable=True),
        sa.Column("llm_model_used", sa.Text, nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Analytics (daily per-account)
    op.create_table(
        "analytics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("linkedin_account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("linkedin_accounts.id", ondelete="CASCADE"), index=True),
        sa.Column("date", sa.Date, index=True),
        sa.Column("connections_sent", sa.Integer, default=0),
        sa.Column("connections_accepted", sa.Integer, default=0),
        sa.Column("messages_sent", sa.Integer, default=0),
        sa.Column("messages_received", sa.Integer, default=0),
        sa.Column("profile_views", sa.Integer, default=0),
        sa.Column("posts_created", sa.Integer, default=0),
        sa.Column("post_impressions", sa.Integer, default=0),
        sa.Column("post_engagements", sa.Integer, default=0),
        sa.Column("connection_acceptance_rate", sa.Float, default=0.0),
        sa.Column("reply_rate", sa.Float, default=0.0),
        sa.Column("meeting_rate", sa.Float, default=0.0),
        sa.Column("risk_score", sa.Integer, default=0),
        sa.Column("risk_factors", postgresql.JSONB, nullable=True),
        sa.Column("limits_snapshot", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Campaign Analytics (daily per-campaign)
    op.create_table(
        "campaign_analytics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), index=True),
        sa.Column("date", sa.Date, index=True),
        sa.Column("leads_discovered", sa.Integer, default=0),
        sa.Column("invites_sent", sa.Integer, default=0),
        sa.Column("connections_made", sa.Integer, default=0),
        sa.Column("messages_sent", sa.Integer, default=0),
        sa.Column("replies_received", sa.Integer, default=0),
        sa.Column("positive_replies", sa.Integer, default=0),
        sa.Column("meetings_booked", sa.Integer, default=0),
        sa.Column("conversion_rate", sa.Float, default=0.0),
        sa.Column("message_performance", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("campaign_analytics")
    op.drop_table("analytics")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("leads")
    op.drop_table("campaigns")
    op.drop_table("linkedin_accounts")
    op.drop_table("subscriptions")
    op.drop_table("users")

    # Drop enums
    for name in [
        "userrole", "subscriptiontier", "subscriptionstatus",
        "accounttype", "accountstatus", "campaigntype", "campaignstatus",
        "leadstatus", "conversationintent", "messagedirection", "messagetype",
    ]:
        op.execute(f"DROP TYPE IF EXISTS {name}")
