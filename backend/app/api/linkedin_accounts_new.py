"""LinkedIn account management endpoints (VNC-based only)."""

from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.campaign import Campaign
from app.models.linkedin_account import LinkedInAccount
from app.models.user import User
from app.schemas.user import LinkedInAccountResponse

router = APIRouter(prefix="/linkedin-accounts", tags=["linkedin-accounts"])


@router.get("/", response_model=list[LinkedInAccountResponse])
async def list_accounts(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all LinkedIn accounts for the current user."""
    result = await db.execute(
        select(LinkedInAccount).where(LinkedInAccount.user_id == user.id)
    )
    return result.scalars().all()


@router.get("/{account_id}", response_model=LinkedInAccountResponse)
async def get_account(
    account_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific LinkedIn account."""
    result = await db.execute(
        select(LinkedInAccount).where(
            LinkedInAccount.id == account_id,
            LinkedInAccount.user_id == user.id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return account


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    account_id: uuid.UUID,
    force: bool = Query(default=False),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a LinkedIn account."""
    result = await db.execute(
        select(LinkedInAccount).where(
            LinkedInAccount.id == account_id,
            LinkedInAccount.user_id == user.id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    campaign_count = await db.scalar(
        select(func.count(Campaign.id)).where(
            Campaign.user_id == user.id,
            Campaign.linkedin_account_id == account_id,
        )
    )
    if (campaign_count or 0) > 0 and not force:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Account is associated with {campaign_count} campaign(s). Delete campaigns first or retry with force=true.",
        )

    await db.delete(account)
    await db.flush()
    return None
