"""User & auth schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


# ── Auth ────────────────────────────────────────────────────
class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenRefresh(BaseModel):
    refresh_token: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1, max_length=255)


class GoogleAuthCallback(BaseModel):
    code: str
    state: Optional[str] = None


# ── User CRUD ───────────────────────────────────────────────
class UserBase(BaseModel):
    email: EmailStr
    full_name: str


class UserCreate(UserBase):
    password: str = Field(min_length=8)


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None


class UserResponse(UserBase):
    id: uuid.UUID
    role: str
    is_active: bool
    is_verified: bool
    avatar_url: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── LinkedIn Account ───────────────────────────────────────
class LinkedInAccountCreate(BaseModel):
    linkedin_email: EmailStr
    linkedin_password: str
    account_type: str = "normal"
    proxy_url: Optional[str] = None


class LinkedInAccountResponse(BaseModel):
    id: uuid.UUID
    linkedin_email: str
    linkedin_name: Optional[str] = None
    linkedin_profile_url: Optional[str] = None
    account_type: str
    status: str
    is_warming_up: bool
    warmup_day: int
    risk_score: int
    last_active_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Subscription ────────────────────────────────────────────
class SubscriptionResponse(BaseModel):
    id: uuid.UUID
    tier: str
    status: str
    max_linkedin_accounts: int
    max_active_campaigns: int
    started_at: datetime
    expires_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
