"""LinkedIn account management endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.campaign import Campaign
from app.models.linkedin_account import LinkedInAccount, AccountType, AccountStatus
from app.models.user import User
from app.schemas.user import LinkedInAccountCreate, LinkedInAccountResponse
from app.security import encrypt_value

router = APIRouter(prefix="/linkedin-accounts", tags=["linkedin-accounts"])


@router.get("/", response_model=list[LinkedInAccountResponse])
async def list_accounts(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(LinkedInAccount).where(LinkedInAccount.user_id == user.id)
    )
    return result.scalars().all()


@router.post("/", response_model=LinkedInAccountResponse, status_code=status.HTTP_201_CREATED)
async def add_account(
    body: LinkedInAccountCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    normalized_email = body.linkedin_email.strip().lower()
    result = await db.execute(
        select(LinkedInAccount).where(
            LinkedInAccount.user_id == user.id,
            LinkedInAccount.linkedin_email == normalized_email,
        )
        .limit(1)
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="LinkedIn account already exists",
        )

    account = LinkedInAccount(
        user_id=user.id,
        linkedin_email=normalized_email,
        encrypted_password=encrypt_value(body.linkedin_password),
        account_type=AccountType(body.account_type),
        status=AccountStatus.SESSION_EXPIRED,
        proxy_url=body.proxy_url,
    )
    db.add(account)
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="LinkedIn account already exists",
        )
    await db.refresh(account)
    return account


@router.get("/{account_id}", response_model=LinkedInAccountResponse)
async def get_account(
    account_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
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


@router.post("/{account_id}/login", response_model=LinkedInAccountResponse)
async def trigger_login(
    account_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger a Playwright-based LinkedIn login for the account.

    This enqueues a Celery task that opens a browser, logs in,
    and stores the encrypted session cookies.
    """
    result = await db.execute(
        select(LinkedInAccount).where(
            LinkedInAccount.id == account_id,
            LinkedInAccount.user_id == user.id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    from app.tasks.campaign_tasks import linkedin_login_task
    try:
        linkedin_login_task.delay(str(account.id))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to queue login task: {e}",
        )

    return account
