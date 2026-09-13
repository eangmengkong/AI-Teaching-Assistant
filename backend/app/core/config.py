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
    # Transient scratch directory used while processing an upload. The actual
    # file bytes live in Cloudflare R2 (or Document.file_data as a fallback),
    # so keeping the disk copy here is fine even on Render's ephemeral file
    # system.
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "./uploads")

    # Cloudflare R2 object storage: stores the actual uploaded file bytes so the
    # database (Neon free = 5 GB transfer/month) is never loaded with multi-MB
    # PDFs. R2 is S3-compatible -> talk to it with boto3.
    # Create R2 -> API Tokens -> "Manage R2 Tokens" -> create a token with
    # Object Read & Write scoped to one bucket, then set these four values.
    R2_ACCOUNT_ID: str = os.getenv("R2_ACCOUNT_ID", "")
    R2_ACCESS_KEY_ID: str = os.getenv("R2_ACCESS_KEY_ID", "")
    R2_SECRET_ACCESS_KEY: str = os.getenv("R2_SECRET_ACCESS_KEY", "")
    R2_BUCKET: str = os.getenv("R2_BUCKET", "")

    # ---------------------------------------------------------------------------
    # OCR fallback (scanned/image-only PDFs). pypdf extracts 0 characters from
    # image-only pages, so when a PDF has essentially no text and an AI vision
    # provider is configured, each page is rendered to an image and transcribed
    # by the AI (Gemini vision works great for Khmer/Chinese textbooks).
    # ---------------------------------------------------------------------------
    OCR_ENABLED: bool = os.getenv("OCR_ENABLED", "true").strip().lower() in (
        "1", "true", "yes", "on"
    )
    # Safety caps: a whole scanned textbook is hundreds of vision calls, so
    # bound both the page count and the pace (free tiers are rate-limited).
    OCR_MAX_PAGES: int = int(os.getenv("OCR_MAX_PAGES", "400"))
    # Seconds between vision requests (Gemini free ~10 RPM -> keep >= 6).
    OCR_REQUEST_INTERVAL: float = float(os.getenv("OCR_REQUEST_INTERVAL", "6"))
    # Render resolution for page images (higher = better OCR, bigger payload).
    OCR_IMAGE_DPI: int = int(os.getenv("OCR_IMAGE_DPI", "110"))
    # A page is considered "textless" when the whole PDF yields fewer chars
    # than this per page on average (cover pages may carry a little text).
    OCR_MIN_CHARS_PER_PAGE: int = int(os.getenv("OCR_MIN_CHARS_PER_PAGE", "20"))

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
