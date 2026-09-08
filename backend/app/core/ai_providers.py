"""
Multi-provider AI client with automatic fallback.

Providers are tried in order until one answers. A provider that fails
(rate limit, quota exhausted, bad key, network error, ...) is put on a
short cooldown so the chain keeps working with the remaining providers.

Configuration (backend/.env):
    OPENAI_API_KEY / OPENAI_MODEL / OPENAI_BASE_URL   -> primary provider
    AI_FALLBACK_1_API_KEY / _MODEL / _BASE_URL        -> fallback 1
    AI_FALLBACK_2_API_KEY / _MODEL / _BASE_URL        -> fallback 2
    ... up to AI_FALLBACK_9_*
"""
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings

try:
    import openai
except ImportError:  # pragma: no cover
    openai = None

logger = logging.getLogger("ai_providers")


@dataclass
class AIProvider:
    name: str
    api_key: str
    model: str
    base_url: Optional[str] = None


# provider name -> monotonic timestamp until which it is skipped
_cooldown_until: Dict[str, float] = {}

_MAX_FALLBACK_SLOTS = 9


def _is_placeholder(key: str) -> bool:
    """Detect unfilled .env placeholders like 'sk-proj-your-openai-api-key-here'."""
    k = (key or "").strip().lower()
    return (not k) or "your-" in k


# .env file values are NOT process environment variables, so AI_FALLBACK_* must
# be readable from both places. Cache the parsed file once.
_ENV_FILE_CACHE: Dict[str, str] = {}


def _load_env_file() -> Dict[str, str]:
    """Parse backend/.env (KEY=VALUE lines) into a dict, once per process."""
    if not _ENV_FILE_CACHE:
        here = os.path.dirname(os.path.abspath(__file__))          # backend/app/core
        candidates = [
            os.path.join(here, "..", "..", ".env"),                # backend/.env
            os.path.join(os.getcwd(), ".env"),                     # cwd fallback
        ]
        for path in candidates:
            real = os.path.normpath(path)
            if os.path.exists(real):
                try:
                    with open(real, "r", encoding="utf-8") as fh:
                        for line in fh:
                            line = line.strip()
                            if not line or line.startswith("#") or "=" not in line:
                                continue
                            key, _, val = line.partition("=")
                            _ENV_FILE_CACHE[key.strip()] = val.strip().strip('"').strip("'")
                except OSError:
                    pass
                break
    return _ENV_FILE_CACHE


def _env(name: str, default: str = "") -> str:
    """Read an env var from the process environment first, then from .env file."""
    val = os.getenv(name)
    if val is not None and val.strip():
        return val.strip()
    return _load_env_file().get(name, default)


def get_provider_chain() -> List[AIProvider]:
    """Build the ordered provider chain from environment configuration."""
    chain: List[AIProvider] = []

    # 1) Primary provider — classic OPENAI_* variables (base URL optional,
    #    so Gemini/Groq/etc. set via OPENAI_BASE_URL are covered too).
    if settings.OPENAI_API_KEY and not _is_placeholder(settings.OPENAI_API_KEY):
        chain.append(
            AIProvider(
                name="primary",
                api_key=settings.OPENAI_API_KEY.strip(),
                model=settings.OPENAI_MODEL.strip(),
                base_url=(settings.OPENAI_BASE_URL or "").strip() or None,
            )
        )

    # 2) Fallbacks — AI_FALLBACK_1_*, AI_FALLBACK_2_*, ... AI_FALLBACK_9_*
    for i in range(1, _MAX_FALLBACK_SLOTS + 1):
        api_key = _env(f"AI_FALLBACK_{i}_API_KEY")
        model = _env(f"AI_FALLBACK_{i}_MODEL")
        base_url = _env(f"AI_FALLBACK_{i}_BASE_URL") or None
        if api_key and model and not _is_placeholder(api_key):
            chain.append(
                AIProvider(name=f"fallback_{i}", api_key=api_key, model=model, base_url=base_url)
            )

    return chain


def _to_tools_format(functions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert legacy function definitions ({'name', 'description',
    'parameters'}) to the modern tools format accepted by OpenAI, Groq and
    Gemini's OpenAI-compatible endpoint (the legacy 'functions=' payload is
    rejected by Gemini with 400 INVALID_ARGUMENT)."""
    out: List[Dict[str, Any]] = []
    for fn in functions or []:
        if "type" in fn and "function" in fn:
            out.append(fn)
        else:
            out.append({"type": "function", "function": fn})
    return out


async def chat_with_fallback(
    messages: List[Dict[str, Any]],
    functions: Optional[List[Dict[str, Any]]] = None,
    function_call: str = "auto",
) -> Tuple[Optional[Any], str]:
    """
    Run one chat.completions call against every configured provider in order.
    Function definitions are sent in the modern 'tools' format regardless of
    the legacy parameter name used by callers.

    Returns:
        (response, provider_name)  on success — response is the SDK object.
        (None, error_summary)      if every provider failed.
    """
    if openai is None:
        return None, "openai package not installed"

    providers = get_provider_chain()
    if not providers:
        return None, "no AI providers configured (set OPENAI_API_KEY or AI_FALLBACK_* in .env)"

    now = time.monotonic()
    available = [p for p in providers if _cooldown_until.get(p.name, 0) <= now]
    # If every provider is cooling down, still try them in the original order.
    ordered = available if available else providers

    tools = _to_tools_format(functions) if functions else None
    errors: List[str] = []
    for provider in ordered:
        try:
            client = openai.AsyncOpenAI(
                api_key=provider.api_key,
                base_url=provider.base_url,
                timeout=settings.AI_PROVIDER_TIMEOUT_SECONDS,
            )
            kwargs: Dict[str, Any] = {"model": provider.model, "messages": messages}
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"
            response = await client.chat.completions.create(**kwargs)
            logger.info("AI provider '%s' (%s) responded", provider.name, provider.model)
            return response, provider.name
        except Exception as exc:  # noqa: BLE001 — any provider error triggers fallback
            cooldown = settings.AI_PROVIDER_COOLDOWN_SECONDS
            _cooldown_until[provider.name] = time.monotonic() + cooldown
            logger.warning(
                "AI provider '%s' (%s) failed: %s — cooling down %ss, trying next",
                provider.name, provider.model, exc, cooldown,
            )
            errors.append(f"{provider.name}: {exc}")

    return None, " | ".join(errors)


def reset_cooldowns() -> None:
    """Clear all provider cooldowns (used by tests / manual retry)."""
    _cooldown_until.clear()