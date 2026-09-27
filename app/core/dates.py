"""Dates in the shop's own timezone (Pakistan by default)."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

DEFAULT_TZ = "Asia/Karachi"


def today(timezone: str | None = None) -> date:
    return datetime.now(ZoneInfo(timezone or DEFAULT_TZ)).date()


def short_date(d: date) -> str:
    """28 Sep"""
    return f"{d.day} {d:%b}"
