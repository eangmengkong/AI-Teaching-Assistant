import os
from pydantic_settings import BaseSettings
from typing import Optional, List

class Settings(BaseSettings):
    PROJECT_NAME: str = "AI Teaching Assistant"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = os.getenv("SECRET_KEY", "super-secret-key-change-in-production-2026")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7 # 7 days

    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", 
        "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_teaching_assistant"
    )
    SYNC_DATABASE_URL: str = os.getenv(
        "SYNC_DATABASE_URL", 
        "postgresql://postgres:postgres@localhost:5432/ai_teaching_assistant"
    )

    # OpenAI / AI Agent (works with any OpenAI-compatible provider)
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")
    # Optional: point at a free OpenAI-compatible provider (Gemini/Groq/OpenRouter/Ollama).
    # Leave empty to use real OpenAI.
    OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "")

    # AI fallback chain behaviour
    AI_PROVIDER_COOLDOWN_SECONDS: int = int(os.getenv("AI_PROVIDER_COOLDOWN_SECONDS", "300"))
    AI_PROVIDER_TIMEOUT_SECONDS: int = int(os.getenv("AI_PROVIDER_TIMEOUT_SECONDS", "120"))

    # Telegram
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_WEBHOOK_URL: Optional[str] = os.getenv("TELEGRAM_WEBHOOK_URL", None)

    # Daily automation (runs inside the background worker - works without your PC)
    DAILY_DIGEST_ENABLED: bool = os.getenv("DAILY_DIGEST_ENABLED", "true").lower() in ("1", "true", "yes", "on")
    DAILY_DIGEST_HOUR: int = int(os.getenv("DAILY_DIGEST_HOUR", "7"))  # local course-timezone hour
    GOOGLE_CALENDAR_SYNC_ENABLED: bool = os.getenv("GOOGLE_CALENDAR_SYNC_ENABLED", "true").lower() in ("1", "true", "yes", "on")

    # Google Calendar OAuth
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI: str = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/v1/calendar/oauth2callback")

    # Frontend base URL — used to build password-reset links sent via Telegram
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")

    # Upload storage
    MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "500"))
    # Transient scratch directory used while processing an upload. The natural
    # home for the file bytes is the database (Document.file_data), so keeping
    # the disk copy here is fine even on Render's ephemeral file system.
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "./uploads")

    # Allowed browser origins for CORS (comma-separated in the CORS_ORIGINS env
    # var). Origins must be explicit: the "*" wildcard cannot be combined with
    # allow_credentials=True, so a fixed allow-list is the only spec-compliant
    # way to keep both cross-origin requests AND Authorization headers working.
    CORS_ORIGINS: List[str] = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:3000,https://ai-teaching-assistant-eight.vercel.app",
        ).split(",")
        if origin.strip()
    ]

    class Config:
        case_sensitive = True
        env_file = ".env"
        extra = "ignore"  # .env may contain extra keys (e.g. AI_FALLBACK_*) read elsewhere

settings = Settings()
