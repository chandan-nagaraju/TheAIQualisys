"""Canonical calendar dates for billing and subscription logic (UTC)."""

from __future__ import annotations

from datetime import date, datetime, timezone


def billing_today() -> date:
    """Single source of truth for trial/subscription comparisons (avoids local vs UTC drift)."""
    return datetime.now(timezone.utc).date()
