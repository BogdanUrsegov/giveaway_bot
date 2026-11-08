"""Environment-backed application settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_list(name: str) -> frozenset[int]:
    raw = os.getenv(name, "")
    result: set[int] = set()
    for item in raw.split(","):
        item = item.strip()
        if item:
            try:
                result.add(int(item))
            except ValueError as exc:
                raise ValueError(f"{name} must contain comma-separated integer Telegram IDs") from exc
    return frozenset(result)


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    admin_ids: frozenset[int]
    db_path: str
    timezone: str
    log_level: str
    paid_giveaways_enabled: bool
    required_channel_url: str | None
    support_contact: str
    terms_url: str | None
    terms_version: str
    privacy_url: str | None
    legal_review_confirmed: bool
    legal_review_reference: str | None


def load_settings() -> Settings:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise ValueError("BOT_TOKEN is required. Copy .env.example to .env and set your token.")
    admin_ids = _int_list("ADMIN_IDS")
    if not admin_ids:
        raise ValueError("ADMIN_IDS must contain at least one Telegram user ID")
    timezone = os.getenv("TIMEZONE", "Europe/Moscow").strip()
    # Validate the IANA timezone early, before the bot starts polling.
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown TIMEZONE: {timezone}") from exc

    db_path = os.getenv("DB_PATH", "/app/data/giveaways.db").strip()
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    paid_enabled = _bool("PAID_GIVEAWAYS_ENABLED", False)
    terms_url = os.getenv("TERMS_URL") or None
    privacy_url = os.getenv("PRIVACY_URL") or None
    legal_review_confirmed = _bool("LEGAL_REVIEW_CONFIRMED", False)
    legal_review_reference = os.getenv("LEGAL_REVIEW_REFERENCE") or None
    if paid_enabled:
        from urllib.parse import urlparse

        def is_public_https_url(value: str | None) -> bool:
            if not value or "example.com" in value.lower():
                return False
            parsed = urlparse(value)
            return parsed.scheme == "https" and bool(parsed.netloc)

        missing = []
        if not legal_review_confirmed:
            missing.append("LEGAL_REVIEW_CONFIRMED=true")
        if not legal_review_reference:
            missing.append("LEGAL_REVIEW_REFERENCE (internal legal review/license reference)")
        if not is_public_https_url(terms_url):
            missing.append("TERMS_URL (public HTTPS page with reviewed rules)")
        if not is_public_https_url(privacy_url):
            missing.append("PRIVACY_URL (public HTTPS privacy notice)")
        if missing:
            raise ValueError(
                "Paid chance-based giveaways are fail-closed. Before enabling them, "
                "complete the operator's platform/legal review and configure: " + "; ".join(missing)
            )

    return Settings(
        bot_token=token,
        admin_ids=admin_ids,
        db_path=db_path,
        timezone=timezone,
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        paid_giveaways_enabled=paid_enabled,
        required_channel_url=os.getenv("REQUIRED_CHANNEL_URL") or None,
        support_contact=os.getenv("SUPPORT_CONTACT", "the bot administrator"),
        terms_url=terms_url,
        terms_version=os.getenv("TERMS_VERSION", "1"),
        privacy_url=privacy_url,
        legal_review_confirmed=legal_review_confirmed,
        legal_review_reference=legal_review_reference,
    )


settings = load_settings()
