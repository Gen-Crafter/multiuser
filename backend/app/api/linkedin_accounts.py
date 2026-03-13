"""LinkedIn account management endpoints."""

from __future__ import annotations

import datetime as _dt
import json as _json
import time as _time
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

    # ── Step 1: parse stored cookies ─────────────────────────────────────────
    try:
        from app.security import decrypt_value
        raw = decrypt_value(account.encrypted_cookies)
        data = _json.loads(raw)
        cookie_list = data if isinstance(data, list) else data.get("cookies", [])
        li_at_cookie = next((c for c in cookie_list if isinstance(c, dict) and c.get("name") == "li_at"), None)
        if not li_at_cookie:
            return {"valid": False, "reason": "li_at cookie not found in stored session."}
        li_at = li_at_cookie["value"]
    except Exception as e:
        return {"valid": False, "reason": f"Failed to decrypt/parse cookies: {e}"}

    # ── Step 2: check expiry date from the cookie itself (no network needed) ─
    expiry_ts = li_at_cookie.get("expirationDate") or li_at_cookie.get("expires")
    if expiry_ts and isinstance(expiry_ts, (int, float)):
        if expiry_ts < _time.time():
            exp_str = _dt.datetime.utcfromtimestamp(expiry_ts).strftime("%Y-%m-%d %H:%M UTC")
            return {
                "valid": False,
                "reason": f"li_at cookie expired on {exp_str}. Re-import fresh cookies from your browser.",
            }
        else:
            exp_str = _dt.datetime.utcfromtimestamp(expiry_ts).strftime("%Y-%m-%d")
            expiry_info = f"expires {exp_str}"
    else:
        expiry_info = "no expiry field"

    # ── Step 3: live HTTP check (only if account has a proxy configured) ──────
    has_proxy = bool(getattr(account, "proxy_url", None))
    if has_proxy:
        cookie_str = "; ".join(
            f"{c['name']}={c['value']}"
            for c in cookie_list
            if isinstance(c, dict) and c.get("name") and c.get("value")
        )
        headers = {
            "cookie": cookie_str,
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "en-US,en;q=0.9",
        }
        try:
            proxies = {"http://": account.proxy_url, "https://": account.proxy_url}
            async with httpx.AsyncClient(timeout=20, follow_redirects=True, proxies=proxies) as client:
                resp = await client.get("https://www.linkedin.com/feed/", headers=headers)
            final_url = str(resp.url)
            if "/feed" in final_url and "login" not in final_url:
                return {"valid": True, "name": f"✓ Live check passed via proxy ({expiry_info})"}
            elif any(k in final_url for k in ("login", "authwall", "signup", "checkpoint")):
                return {
                    "valid": False,
                    "reason": f"LinkedIn rejected the session via proxy. Re-import fresh cookies. ({expiry_info})",
                }
            else:
                return {"valid": True, "name": f"li_at present ({expiry_info})"}
        except Exception as e:
            # Proxy check failed — fall through to cookie-only result
            pass

    # ── Step 4: no proxy — return cookie-local result with honest caveat ──────
    return {
        "valid": True,
        "name": (
            f"Cookie present & not expired ({expiry_info}). "
            "Live check skipped — server IP differs from where cookies were issued. "
            "Add a proxy_url on this account to enable live verification."
        ),
    }


@router.post("/import-from-keeper", response_model=LinkedInAccountResponse)
async def import_from_keeper(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Import LinkedIn session from the keeper service."""
    import httpx
    
    try:
        # Get session info from keeper
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get("http://linkedin-keeper:3001/session-info")
            if resp.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Keeper service not available or no active session",
                )
            session_data = resp.json()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to connect to keeper service: {e}",
        )
    
    if not session_data.get("has_session"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active LinkedIn session in keeper. Start automation first.",
        )
    
    # Extract cookies from keeper
    try:
        cookies_resp = await httpx.AsyncClient(timeout=10).get("http://linkedin-keeper:3001/export-cookies")
        if cookies_resp.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Failed to export cookies from keeper",
            )
        cookies_json = cookies_resp.text
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to export cookies: {e}",
        )
    
    # Get email from session
    email = session_data.get("email", "keeper-session@example.com")
    
    # Check if account already exists
    result = await db.execute(
        select(LinkedInAccount).where(
            LinkedInAccount.user_id == user.id,
            LinkedInAccount.linkedin_email == email,
        )
        .limit(1)
    )
    existing = result.scalar_one_or_none()
    if existing:
        # Update existing account with new cookies
        existing.encrypted_cookies = encrypt_value(cookies_json)
        existing.status = AccountStatus.ACTIVE
        existing.checkpoint_url = None
        await db.commit()
        await db.refresh(existing)
        return existing
    
    # Create new account
    account = LinkedInAccount(
        user_id=user.id,
        linkedin_email=email,
        encrypted_password=encrypt_value("imported-from-keeper"),
        account_type=AccountType.PERSONAL,
        status=AccountStatus.ACTIVE,
        encrypted_cookies=encrypt_value(cookies_json),
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return account


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
