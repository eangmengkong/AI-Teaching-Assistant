from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
# pyrefly: ignore [missing-import]
from sqlalchemy.ext.asyncio import AsyncSession
# pyrefly: ignore [missing-import]
from sqlalchemy import select

from app.core.database import get_db
from app.core.config import settings
from app.api.v1.auth import get_current_user
from app.models.models import User, Course, LessonSchedule
from app.services.calendar_service import CalendarService

router = APIRouter()

@router.get("/auth-url")
async def get_calendar_auth_url(current_user: User = Depends(get_current_user)):
    url = CalendarService.get_auth_url()
    has_client_id = bool(settings.GOOGLE_CLIENT_ID)
    connected = bool(current_user.google_refresh_token and has_client_id)
    return {
        "auth_url": url,
        "has_client_id": has_client_id,
        "connected": connected,
    }

@router.get("/oauth2callback")
async def calendar_oauth_callback(
    code: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Google redirects here with ?error=... when the user denies consent
    # or the consent screen fails.
    if error:
        raise HTTPException(status_code=400, detail=f"Google OAuth failed: {error}")
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code from Google")

    token_url = "https://oauth2.googleapis.com/token"
    payload = {
        "code": code,
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code"
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(token_url, data=payload)

    if resp.status_code != 200:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to exchange Google OAuth code: {resp.text}"
        )

    token_data = resp.json()
    refresh_token = token_data.get("refresh_token")
    # Never store an access token in google_refresh_token: CalendarService
    # passes it to Credentials(refresh_token=...) and access tokens expire
    # in about an hour, so they cannot be used to refresh credentials.
    if refresh_token:
        current_user.google_refresh_token = refresh_token
        await db.commit()
        return {
            "status": "success",
            "message": "Google Calendar connected successfully!",
            "saved": True
        }

    if current_user.google_refresh_token:
        return {
            "status": "success",
            "message": "Google Calendar is already connected (kept existing refresh token).",
            "saved": True
        }

    return {
        "status": "error",
        "message": "Google did not return a refresh token. Re-authorize with access_type=offline and prompt=consent.",
        "saved": False
    }

@router.post("/sync/{course_id}")
async def sync_calendar_events(
    course_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    course = (await db.execute(select(Course).where(Course.id == course_id))).scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    s_stmt = select(LessonSchedule).where(LessonSchedule.course_id == course_id)
    schedules = (await db.execute(s_stmt)).scalars().all()

    synced_events = []
    for s in schedules:
        evt_id = await CalendarService.create_calendar_event(db, course, current_user, s)
        synced_events.append({"lesson_id": s.id, "google_event_id": evt_id})

    has_google = bool(current_user.google_refresh_token and settings.GOOGLE_CLIENT_ID)
    return {
        "status": "success",
        "google_connected": has_google,
        "total_synced": len(synced_events),
        "events": synced_events,
        "message": "Events synced to Google Calendar" if has_google else "Events saved locally in DB. Add GOOGLE_CLIENT_ID and complete auth-url to sync directly to Google Calendar."
    }
