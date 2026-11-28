"""Canonical calendar dates for billing and subscription logic (UTC)."""

from __future__ import annotations

import calendar
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


def payment_overdue_close_date(today: date) -> date:
    """The 30th of this month (or the last day if the month is shorter).

    If *today* is already after that date, use the 30th of the next month.
    After this date we close all ties for unpaid accounts.
    """

    def _thirtieth_or_last(year: int, month: int) -> date:
        last = calendar.monthrange(year, month)[1]
        return date(year, month, min(30, last))

    cutoff = _thirtieth_or_last(today.year, today.month)
    if today > cutoff:
        if today.month == 12:
            return _thirtieth_or_last(today.year + 1, 1)
        return _thirtieth_or_last(today.year, today.month + 1)
    return cutoff


def unpaid_month_count(since: date, until: date) -> int:
    """Whole months of unpaid coverage from *since* through *until* (ceil of days/30)."""
    days = (until - since).days
    if days <= 0:
        return 1
    return max(1, (days + 29) // 30)
