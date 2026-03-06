"""LinkedIn account management endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
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
    account = LinkedInAccount(
        user_id=user.id,
        linkedin_email=body.linkedin_email,
        encrypted_password=encrypt_value(body.linkedin_password),
        account_type=AccountType(body.account_type),
        status=AccountStatus.SESSION_EXPIRED,
        proxy_url=body.proxy_url,
    )
    db.add(account)
    await db.flush()
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
    await db.delete(account)
    await db.flush()


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
    linkedin_login_task.delay(str(account.id))

    return account
