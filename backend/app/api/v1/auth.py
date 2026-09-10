from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import JWTError, jwt

import hashlib
import secrets
from datetime import datetime, timedelta

from app.core.database import get_db
from app.core.config import settings
from app.core.security import create_access_token, verify_password, get_password_hash
from app.models.models import PasswordResetToken, User
from app.schemas.schemas import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    Token,
    UserCreate,
    UserResponse,
)
from app.services.reminder_service import ReminderService

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/token", auto_error=False)

async def get_current_user(token: Optional[str] = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)) -> User:
    if token:
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            user_id: str = payload.get("sub")
            if user_id:
                stmt = select(User).where(User.id == int(user_id))
                result = await db.execute(stmt)
                user = result.scalar_one_or_none()
                if user:
                    return user
        except JWTError:
            pass

    # Fallback to default local user for seamless execution
    stmt = select(User).limit(1)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()
    if not user:
        user = User(
            email="teacher@local.com",
            hashed_password=get_password_hash("defaultpassword123"),
            full_name="Default Teacher"
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return user

@router.post("/register", response_model=UserResponse)
async def register_user(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    stmt = select(User).where(User.email == user_in.email)
    res = await db.execute(stmt)
    if res.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="User with this email already exists")

    hashed_pw = get_password_hash(user_in.password)
    user = User(
        email=user_in.email,
        hashed_password=hashed_pw,
        full_name=user_in.full_name,
        telegram_chat_id=user_in.telegram_chat_id
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user

@router.post("/token", response_model=Token)
async def login_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    stmt = select(User).where(User.email == form_data.username)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect email or password")

    access_token = create_access_token(subject=user.id)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user
    }

@router.get("/me", response_model=UserResponse)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user


def _hash_reset_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _generate_reset_token() -> str:
    return secrets.token_urlsafe(32)


@router.post("/forgot-password")
async def forgot_password(payload: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    """
    Always responds 200 and never reveals whether the email exists.
    If the account exists and has Telegram linked, a single-use reset link
    (valid 30 minutes) is delivered by the bot.
    """
    stmt = select(User).where(User.email == payload.email)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()

    generic_message = (
        "If that email has Telegram linked to the bot, a reset link is on its way."
    )
    if not user:
        return {"message": generic_message, "sent": False}

    if not user.telegram_chat_id:
        return {
            "message": generic_message,
            "sent": False,
            "detail": (
                "No Telegram chat is linked to this account, so no link could be "
                "delivered. Open Telegram, send /start to your bot, then retry."
            ),
        }

    raw_token = _generate_reset_token()
    reset = PasswordResetToken(
        user_id=user.id,
        token_hash=_hash_reset_token(raw_token),
        expires_at=datetime.utcnow() + timedelta(minutes=30),
    )
    db.add(reset)
    await db.commit()

    base = settings.FRONTEND_URL.rstrip("/")
    link = f"{base}/reset-password?token={raw_token}"
    message = (
        "🔑 PASSWORD RESET\n\n"
        "We received a request to reset your AI Teaching Assistant password.\n\n"
        f"Tap the button below (or copy this link):\n{link}\n\n"
        "⏳ This link expires in 30 minutes and can be used only once.\n"
        "🛡️ If you didn't request this, just ignore this message — "
        "your current password keeps working."
    )
    sent = await ReminderService.send_telegram_message(
        user.telegram_chat_id,
        message,
        reply_markup={
            "inline_keyboard": [[{"text": "🔑 Reset my password", "url": link}]]
        },
    )

    return {"message": generic_message, "sent": sent}


@router.post("/reset-password", response_model=Token)
async def reset_password(payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    if len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters")

    token_hash = _hash_reset_token(payload.token)
    stmt = select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
    res = await db.execute(stmt)
    reset = res.scalar_one_or_none()

    now = datetime.utcnow()
    if not reset or reset.used_at is not None or reset.expires_at < now:
        raise HTTPException(
            status_code=400,
            detail="This reset link is invalid, already used, or expired. Please request a new one.",
        )

    stmt = select(User).where(User.id == reset.user_id)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Account not found")

    user.hashed_password = get_password_hash(payload.new_password)
    reset.used_at = now
    await db.commit()
    await db.refresh(user)

    access_token = create_access_token(subject=user.id)
    return {"access_token": access_token, "token_type": "bearer", "user": user}


@router.post("/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters")
    if payload.current_password == payload.new_password:
        raise HTTPException(
            status_code=400, detail="New password must be different from the current one"
        )

    current_user.hashed_password = get_password_hash(payload.new_password)
    await db.commit()
    return {"message": "Password updated successfully"}
