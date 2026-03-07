"""LinkedIn account management endpoints."""

from __future__ import annotations

import json as _json
import uuid

import httpx

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.campaign import Campaign
from app.models.linkedin_account import LinkedInAccount, AccountType, AccountStatus
from app.models.user import User
from app.schemas.user import CookieImportBody, LinkedInAccountCreate, LinkedInAccountResponse
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


@router.post("/{account_id}/import-cookies", response_model=LinkedInAccountResponse)
async def import_cookies(
    account_id: uuid.UUID,
    body: CookieImportBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Import browser-exported LinkedIn session cookies directly, bypassing Playwright login."""
    result = await db.execute(
        select(LinkedInAccount).where(
            LinkedInAccount.id == account_id,
            LinkedInAccount.user_id == user.id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    try:
        cookies = _json.loads(body.cookies_json)
        if not isinstance(cookies, list):
            raise ValueError("Expected a JSON array of cookies")
        cookie_names = {c.get("name") for c in cookies if isinstance(c, dict)}
        if not any(n in cookie_names for n in ("li_at", "JSESSIONID", "liap")):
            raise ValueError(
                "No LinkedIn session cookies found. Make sure you exported cookies from linkedin.com"
            )
    except _json.JSONDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid JSON: {e}",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    account.encrypted_cookies = encrypt_value(body.cookies_json)
    account.status = AccountStatus.ACTIVE
    account.checkpoint_url = None
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return account


@router.get("/{account_id}/verify-session")
async def verify_session(
    account_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check whether the stored LinkedIn session cookies are still valid."""
    result = await db.execute(
        select(LinkedInAccount).where(
            LinkedInAccount.id == account_id,
            LinkedInAccount.user_id == user.id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    if not account.encrypted_cookies:
        return {"valid": False, "reason": "No session cookies stored. Use Import Cookies first."}

    try:
        from app.security import decrypt_value
        raw = decrypt_value(account.encrypted_cookies)
        data = _json.loads(raw)
        # Cookie-Editor exports a list; Playwright storage_state has a 'cookies' key
        cookie_list = data if isinstance(data, list) else data.get("cookies", [])
        li_at = next((c["value"] for c in cookie_list if c.get("name") == "li_at"), None)
        if not li_at:
            return {"valid": False, "reason": "li_at cookie not found in stored session."}
    except Exception as e:
        return {"valid": False, "reason": f"Failed to decrypt/parse cookies: {e}"}

    headers = {
        "cookie": f"li_at={li_at}",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
        "accept": "application/json",
        "x-li-lang": "en_US",
        "x-restli-protocol-version": "2.0.0",
    }
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            resp = await client.get(
                "https://www.linkedin.com/voyager/api/identity/profiles/me",
                headers=headers,
            )
        if resp.status_code == 200:
            try:
                profile = resp.json()
                name = (
                    profile.get("miniProfile", {}).get("firstName", "")
                    + " "
                    + profile.get("miniProfile", {}).get("lastName", "")
                ).strip()
            except Exception:
                name = ""
            return {"valid": True, "name": name or "(profile fetched)", "http_status": resp.status_code}
        elif resp.status_code in (401, 403):
            account.status = AccountStatus.SESSION_EXPIRED if hasattr(AccountStatus, 'SESSION_EXPIRED') else AccountStatus.ACTIVE
            return {"valid": False, "reason": "Session expired or revoked by LinkedIn.", "http_status": resp.status_code}
        else:
            return {"valid": False, "reason": f"Unexpected LinkedIn response: {resp.status_code}", "http_status": resp.status_code}
    except httpx.TimeoutException:
        return {"valid": False, "reason": "Request to LinkedIn timed out."}
    except Exception as e:
        return {"valid": False, "reason": f"HTTP error: {e}"}


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
