"""Canonical SaaS billing periods. Matches frontend BILLING_OPTIONS (1m/3m/6m/12m)."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import HTTPException, status

# Stored values on billing_payments.billing_period
PERIOD_MONTHLY = "MONTHLY"
PERIOD_QUARTERLY = "QUARTERLY"
PERIOD_HALF_YEARLY = "HALF_YEARLY"
PERIOD_YEARLY = "YEARLY"

ALLOWED_PERIODS = (PERIOD_MONTHLY, PERIOD_QUARTERLY, PERIOD_HALF_YEARLY, PERIOD_YEARLY)

_PERIOD_BY_ALIAS: dict[str, str] = {
    "1M": PERIOD_MONTHLY,
    "MONTH": PERIOD_MONTHLY,
    "MONTHLY": PERIOD_MONTHLY,
    "3M": PERIOD_QUARTERLY,
    "QUARTER": PERIOD_QUARTERLY,
    "QUARTERLY": PERIOD_QUARTERLY,
    "6M": PERIOD_HALF_YEARLY,
    "HALF": PERIOD_HALF_YEARLY,
    "HALF_YEARLY": PERIOD_HALF_YEARLY,
    "HALF-YEARLY": PERIOD_HALF_YEARLY,
    "12M": PERIOD_YEARLY,
    "YEAR": PERIOD_YEARLY,
    "YEARLY": PERIOD_YEARLY,
}

_LABEL = {
    PERIOD_MONTHLY: "Monthly",
    PERIOD_QUARTERLY: "Quarterly",
    PERIOD_HALF_YEARLY: "Half yearly",
    PERIOD_YEARLY: "Yearly",
}

_DURATION = {
    PERIOD_MONTHLY: "1 Month",
    PERIOD_QUARTERLY: "3 Months",
    PERIOD_HALF_YEARLY: "6 Months",
    PERIOD_YEARLY: "12 Months",
}

# Paid window length after Admin verification (same convention as admin activate:
# subscription_end = start + timedelta(days=N). Monthly: 21-Sep + 30 days = 21-Oct).
_PERIOD_DAYS = {
    PERIOD_MONTHLY: 30,
    PERIOD_QUARTERLY: 90,
    PERIOD_HALF_YEARLY: 180,
    PERIOD_YEARLY: 365,
}


def normalize_billing_period(raw: str | None) -> str:
    if not raw or not str(raw).strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Billing period is required")
    key = str(raw).strip().upper().replace(" ", "_")
    period = _PERIOD_BY_ALIAS.get(key)
    if not period:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid billing period")
    return period


def period_label(period: str) -> str:
    return _LABEL.get(period, period)


def period_duration(period: str) -> str:
    return _DURATION.get(period, period)


def period_length_days(period: str) -> int:
    days = _PERIOD_DAYS.get(period)
    if days is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid billing period")
    return days


def subscription_end_from_start(start: date, period: str) -> date:
    """End date is start plus the period length in days (inclusive last day via `today <= end`)."""
    return start + timedelta(days=period_length_days(period))


def billing_total_inr(
    monthly: int,
    period: str,
    *,
    enterprise: bool,
    yearly_price: int | None = None,
) -> int:
    """Same rules as frontend upgradeHelpers.billingTotalInr, plus optional catalog yearly_price."""
    if period == PERIOD_MONTHLY:
        return monthly
    if period == PERIOD_QUARTERLY:
        return monthly * 3
    if period == PERIOD_HALF_YEARLY:
        return int(round(monthly * 6 - monthly / 2)) if enterprise else monthly * 6
    if period == PERIOD_YEARLY:
        if yearly_price is not None:
            return yearly_price
        return monthly * 11
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid billing period")
