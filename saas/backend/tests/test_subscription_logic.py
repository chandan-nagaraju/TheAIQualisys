"""Subscription helpers (no database when feature flag is off)."""

from datetime import date
from unittest.mock import MagicMock

import pytest

from app.email_util import build_admin_thank_you_email, build_admin_thank_you_performance_email
from app.models import Company, SubscriptionStatus
from app.subscription_logic import (
    can_create_invoice,
    can_access_fir_workspace,
    count_fir_reports_this_month,
    count_fir_reports_total,
    subscription_is_active,
    top_fir_part_report_counts,
)


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


def test_count_fir_reports_total_calls_db() -> None:
    db = MagicMock()
    db.execute.return_value.scalar_one.return_value = 1313
    assert count_fir_reports_total(db, 3) == 1313
    db.execute.assert_called_once()


def test_top_fir_part_report_counts_pads_to_five() -> None:
    db = MagicMock()
    db.execute.return_value.all.return_value = [("P-A", 10), ("P-B", 3)]
    out = top_fir_part_report_counts(db, 1, limit=5)
    assert out[:2] == [("P-A", 10), ("P-B", 3)]
    assert out[2:] == [("—", 0), ("—", 0), ("—", 0)]


def test_thank_you_performance_email_contains_summary_sections() -> None:
    subject, body = build_admin_thank_you_performance_email(
        customer_name="Acme",
        plan_name="Enterprise",
        subscription_start_date="May 1, 2026",
        subscription_end_date="June 18, 2026",
        current_month_name="May 2026",
        current_month_report_count=12,
        total_report_count=100,
        workspace_user_count=3,
        top_parts=[("P1", 40), ("P2", 30), ("P3", 20), ("P4", 7), ("P5", 3)],
        minutes_per_report=15,
    )
    assert "Performance Summary" in subject
    assert "Acme" in body
    assert "**100**" in body or "100" in body
    assert "25.0 hours" in body  # 100 * 15 / 60
    assert "Top 5 Most Frequently Generated Parts" in body


def test_thank_you_send_body_requires_category() -> None:
    from pydantic import ValidationError

    from app.schemas import AdminSubscriptionReminderSendBody

    with pytest.raises(ValidationError):
        AdminSubscriptionReminderSendBody(reminder_type="thank_you")
    with pytest.raises(ValidationError):
        AdminSubscriptionReminderSendBody(reminder_type="ending_soon", thank_you_category="running")
    b = AdminSubscriptionReminderSendBody(reminder_type="thank_you", thank_you_category="new")
    assert b.thank_you_category == "new"


def test_thank_you_tone_varies_by_category() -> None:
    base = dict(
        customer_name="Acme",
        plan_name="Enterprise",
        subscription_start_date="May 1, 2026",
        subscription_end_date="June 18, 2026",
        current_month_name="May 2026",
        current_month_report_count=1,
        total_report_count=10,
        top_parts=[("P1", 4), ("P2", 3), ("P3", 2), ("P4", 1), ("P5", 0)],
    )
    _, running, _, _ = build_admin_thank_you_email(category="running", **base)
    _, stranger, _, _ = build_admin_thank_you_email(category="stranger", **base)
    assert "most active partners" in running
    assert "historical" in stranger.lower()


def test_fir_workspace_requires_trial_or_subscription() -> None:
    c = _company_expired_trial()
    assert can_access_fir_workspace(c, enable_subscription=True, today=date(2026, 3, 1)) is False
