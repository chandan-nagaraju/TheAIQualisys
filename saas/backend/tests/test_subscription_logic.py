"""Subscription helpers (no database when feature flag is off)."""

from datetime import date
from unittest.mock import MagicMock

from app.models import Company, SubscriptionStatus
from app.subscription_logic import can_create_invoice, can_access_fir_workspace, count_fir_reports_this_month, subscription_is_active


def _company_expired_trial() -> Company:
    return Company(
        company_name="Test Co",
        vendor_code="t-vendor-1",
        trial_start_date=date(2020, 1, 1),
        trial_end_date=date(2020, 1, 31),
        subscription_status=SubscriptionStatus.expired.value,
        plan_type="basic",
        subscription_start=None,
        subscription_end=None,
    )


def test_can_create_invoice_disabled_always_allows() -> None:
    c = _company_expired_trial()
    db = MagicMock()
    ok, msg = can_create_invoice(db, c, enable_subscription=False)
    assert ok is True
    assert msg is None
    db.execute.assert_not_called()


def test_subscription_is_active_respects_end_date() -> None:
    c = _company_expired_trial()
    c.subscription_status = SubscriptionStatus.active.value
    c.subscription_start = date(2026, 1, 1)
    c.subscription_end = date(2026, 6, 30)
    assert subscription_is_active(c, today=date(2026, 3, 1)) is True
    assert subscription_is_active(c, today=date(2026, 7, 1)) is False


def test_count_fir_reports_this_month_calls_db() -> None:
    """Monthly FIR usage counts invoice_date within the calendar month of *today*."""
    db = MagicMock()
    db.execute.return_value.scalar_one.return_value = 42
    assert count_fir_reports_this_month(db, 99, today=date(2026, 5, 7)) == 42
    db.execute.assert_called_once()


def test_fir_workspace_requires_trial_or_subscription() -> None:
    c = _company_expired_trial()
    assert can_access_fir_workspace(c, enable_subscription=True, today=date(2026, 3, 1)) is False
