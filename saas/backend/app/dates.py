"""Canonical calendar dates for billing and subscription logic (UTC)."""

from __future__ import annotations

from datetime import date, datetime, timezone


def billing_today() -> date:
    """Single source of truth for trial/subscription comparisons (avoids local vs UTC drift)."""
    return datetime.now(timezone.utc).date()


_ENGLISH_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def billing_month_year_english(d: date | None = None) -> str:
    """Human month label for emails and UI, e.g. ``May 2026`` (always English, not locale-dependent)."""
    d = d or billing_today()
    return f"{_ENGLISH_MONTHS[d.month - 1]} {d.year}"


def format_date_english(d: date) -> str:
    """Full calendar date for emails, e.g. ``June 18, 2026`` (always English)."""
    return f"{_ENGLISH_MONTHS[d.month - 1]} {d.day}, {d.year}"
