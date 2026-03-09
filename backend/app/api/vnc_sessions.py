"""VNC session management endpoints for manual LinkedIn login."""

from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.linkedin_account import LinkedInAccount, AccountStatus
from app.models.user import User
from app.automation.vnc_session_manager import vnc_manager

router = APIRouter(prefix="/vnc-sessions", tags=["vnc-sessions"])


@router.post("/start")
async def start_vnc_session(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start a VNC browser session for manual LinkedIn login."""
    session_id = str(uuid.uuid4())
    
    # Start the VNC session
    session_info = await vnc_manager.start_session(session_id)
    
    return {
        "session_id": session_id,
        "vnc_url": session_info["vnc_url"],
        "debug_url": session_info.get("debug_url"),
        "status": session_info["status"],
        "instructions": {
            "vnc": "Connect to VNC to manually log into LinkedIn",
            "debug": "Use debug URL to view DevTools",
            "next_step": "Call POST /vnc-sessions/{session_id}/save-account after login"
        }
    }


@router.get("/{session_id}/status")
async def get_session_status(
    session_id: str,
    user: User = Depends(get_current_user),
):
    """Check if the user is logged in for the given session."""
    is_logged_in = await vnc_manager.is_logged_in(session_id)
    
    return {
        "session_id": session_id,
        "logged_in": is_logged_in,
        "status": "logged_in" if is_logged_in else "pending_login"
    }


@router.post("/{session_id}/save-account")
async def save_account_from_session(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save the LinkedIn account from the VNC session after manual login."""
    
    # Check if logged in
    if not await vnc_manager.is_logged_in(session_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User not logged in. Please log into LinkedIn first."
        )
    
    # Get cookies and extract email
    encrypted_cookies = await vnc_manager.get_session_cookies(session_id)
    if not encrypted_cookies:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to extract cookies from session."
        )
    
    # Extract LinkedIn email from the session
    linkedin_email = await vnc_manager.get_linkedin_email(session_id)
    if not linkedin_email:
        linkedin_email = "vnc-session@placeholder.com"  # Fallback
    
    # Create LinkedIn account record
    account = LinkedInAccount(
        user_id=user.id,
        linkedin_email=linkedin_email,
        encrypted_cookies=encrypted_cookies,
        status=AccountStatus.ACTIVE,
    )
    
    db.add(account)
    await db.commit()
    await db.refresh(account)
    
    # Cleanup the VNC session
    await vnc_manager.save_and_cleanup(session_id)
    
    return {
        "account_id": str(account.id),
        "linkedin_email": linkedin_email,
        "status": "saved",
        "message": "LinkedIn account saved successfully. You can now create campaigns."
    }


@router.delete("/{session_id}")
async def cleanup_session(
    session_id: str,
    user: User = Depends(get_current_user),
):
    """Manually cleanup a VNC session."""
    await vnc_manager.cleanup()
    return {"status": "cleaned_up"}
