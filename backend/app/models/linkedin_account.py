"""LinkedIn account model with encrypted session storage."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AccountType(str, enum.Enum):
    NORMAL = "normal"
    PREMIUM = "premium"


class AccountStatus(str, enum.Enum):
    ACTIVE = "active"
    SESSION_EXPIRED = "session_expired"
    SUSPENDED = "suspended"
    COOLDOWN = "cooldown"
    WARMUP = "warmup"


class LinkedInAccount(Base):
    __tablename__ = "linkedin_accounts"

    __table_args__ = (
        UniqueConstraint("user_id", "linkedin_email", name="uq_linkedin_accounts_user_email"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    linkedin_email: Mapped[str] = mapped_column(String(320), nullable=False)
    linkedin_name: Mapped[str] = mapped_column(String(255), nullable=True)
    linkedin_profile_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    account_type: Mapped[AccountType] = mapped_column(Enum(AccountType), default=AccountType.NORMAL)
    status: Mapped[AccountStatus] = mapped_column(Enum(AccountStatus), default=AccountStatus.SESSION_EXPIRED)

    # Encrypted session cookies (Fernet encrypted JSON)
    encrypted_cookies: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Encrypted LinkedIn password (for auto-relogin)
    encrypted_password: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Proxy assignment
    proxy_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Browser fingerprint config
    fingerprint_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Warmup tracking
    is_warming_up: Mapped[bool] = mapped_column(Boolean, default=True)
    warmup_day: Mapped[int] = mapped_column(default=0)

    # Risk score 0-100
    risk_score: Mapped[int] = mapped_column(default=0)

    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    user = relationship("User", back_populates="linkedin_accounts")
    campaigns = relationship("Campaign", back_populates="linkedin_account", cascade="all, delete-orphan")
    leads = relationship("Lead", back_populates="linkedin_account", cascade="all, delete-orphan")
