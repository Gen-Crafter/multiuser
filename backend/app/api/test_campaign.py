"""Test endpoint to force-run campaigns immediately, bypassing all checks."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.automation.browser_manager import browser_manager
from app.automation.linkedin_actions import LinkedInActions
from app.database import get_db
from app.models.campaign import Campaign
from app.models.linkedin_account import LinkedInAccount
from app.models.user import User

router = APIRouter(prefix="/test", tags=["test"])


@router.post("/run-campaign/{campaign_id}")
async def force_run_campaign(
    campaign_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Force-run a campaign immediately, bypassing all checks (for testing only)."""
    
    result = await db.execute(
        select(Campaign).where(
            Campaign.id == campaign_id,
            Campaign.user_id == user.id,
        )
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    acct_result = await db.execute(
        select(LinkedInAccount).where(LinkedInAccount.id == campaign.linkedin_account_id)
    )
    account = acct_result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="LinkedIn account not found")

    # Get browser session
    session = await browser_manager.get_session(
        str(account.id),
        encrypted_cookies=account.encrypted_cookies,
        fingerprint_config=account.fingerprint_config,
        proxy_url=account.proxy_url,
    )

    actions = LinkedInActions(browser_manager)

    # Quick test: navigate to LinkedIn feed
    try:
        await session.page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30000)
        current_url = session.page.url
        
        if "/feed" in current_url:
            status = "✓ Session valid - on feed page"
        elif any(x in current_url for x in ["/login", "/authwall", "/checkpoint"]):
            status = f"✗ Session invalid - redirected to {current_url}"
        else:
            status = f"? Unknown state - at {current_url}"

        # Try a simple search
        search_result = await actions.search_people(session, "software engineer", max_results=3)
        
        await browser_manager.release_session(str(account.id))
        
        return {
            "campaign_id": str(campaign_id),
            "campaign_name": campaign.name,
            "account_email": account.linkedin_email,
            "session_status": status,
            "search_test": {
                "query": "software engineer",
                "results_found": len(search_result),
                "sample": search_result[:2] if search_result else [],
            },
        }
    except Exception as e:
        await browser_manager.release_session(str(account.id))
        raise HTTPException(status_code=500, detail=f"Test failed: {str(e)}")
