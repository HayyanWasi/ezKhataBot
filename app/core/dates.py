"""Dates in the shop's own timezone (Pakistan by default)."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

DEFAULT_TZ = "Asia/Karachi"


def now(timezone: str | None = None) -> datetime:
    return datetime.now(ZoneInfo(timezone or DEFAULT_TZ))


def today(timezone: str | None = None) -> date:
    return now(timezone).date()


def short_date(d: date) -> str:
    """28 Sep"""
    return f"{d.day} {d:%b}"
