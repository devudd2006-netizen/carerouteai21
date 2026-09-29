"""CareRoute AI — configuration. All secrets come from environment variables.

Master-prompt contract (§45):
    GOOGLE_MAPS_API_KEY=   enables live Google Places hospital discovery
    GEMINI_API_KEY=        enables the Gemini LLM for summaries (AI engine)
    DATABASE_URL=          database connection (SQLite in prototype, PostgreSQL in production)
    AUTH_SECRET=           JWT signing secret (SECRET_KEY alias kept for compatibility)

Every key is optional: when absent the platform degrades honestly (Places discovery
falls back to the verified prototype directory; the AI falls back to the transparent
deterministic summarizer). Secrets never reach the frontend.
"""
import os
import secrets

from pydantic_settings import BaseSettings


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


class Settings(BaseSettings):
    APP_NAME: str = "CareRoute AI"
    TAGLINE: str = "One Care Journey. Every Right Connection."
    ENVIRONMENT: str = os.environ.get("ENVIRONMENT", "prototype")

    # AUTH_SECRET is the documented name; SECRET_KEY keeps older deployments working.
    SECRET_KEY: str = _env("AUTH_SECRET") or _env("SECRET_KEY") or secrets.token_hex(32)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # AI provider — GEMINI_API_KEY per master prompt, AI_API_KEY kept as generic alias.
    AI_API_KEY: str = _env("GEMINI_API_KEY") or _env("AI_API_KEY")  # server-side only
    AI_BASE_URL: str = os.environ.get("AI_BASE_URL", "https://api.openai.com/v1")
    AI_MODEL: str = os.environ.get("AI_MODEL", "gpt-4o-mini")

    # Google Maps Platform — Places API for dynamic, location-based hospital discovery.
    GOOGLE_MAPS_API_KEY: str = _env("GOOGLE_MAPS_API_KEY")
    # When configured, the same public Places provider can discover nearby medical/health camps.
    # No patient data or hospital EHR data is sent to this provider.
    MEDICAL_CAMPS_LIVE: bool = os.environ.get("MEDICAL_CAMPS_LIVE", "1").lower() not in {"0", "false", "no"}

    # Demo-only routing: one student acting as hospital staff can receive appointment
    # requests for any publicly discovered hospital. Disable this for a real deployment
    # where each hospital must be connected to its own authorized staff account.
    DEMO_APPOINTMENT_ROUTING: bool = os.environ.get("DEMO_APPOINTMENT_ROUTING", "1").lower() not in {"0", "false", "no"}

    # Break-glass access is deliberately short-lived.
    BREAK_GLASS_MINUTES: int = 60
    BREAK_GLASS_JUSTIFICATION_HOURS: int = 24


settings = Settings()
