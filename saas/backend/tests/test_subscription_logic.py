"""Subscription helpers (no database when feature flag is off)."""

from datetime import date
from unittest.mock import MagicMock

import pytest

from app.email_util import (
    build_admin_thank_you_all_email,
    build_admin_thank_you_email,
    build_admin_thank_you_performance_email,
)
from app.models import Company, SubscriptionStatus
from app.subscription_logic import (
    can_create_invoice,
    can_access_fir_workspace,
    count_fir_reports_this_month,
    count_fir_reports_total,
    subscription_is_active,
    top_fir_part_report_counts,
    _median_gap_days_consecutive,
)


def sample_thank_you_top_parts() -> list[tuple[str, int, str, str]]:
    return [
        ("P1", 40, "7", "May 15, 2026"),
        ("P2", 30, "14", "April 1, 2026"),
        ("P3", 20, "10", "March 10, 2026"),
        ("P4", 7, "3", "February 2, 2026"),
        ("P5", 3, "1", "January 1, 2026"),
    ]


def sample_thank_you_all_engagement_sections() -> list[
    tuple[str, int, int, list[tuple[str, int, str, str]]]
]:
    """Synthetic per-band sections (each with a distinct Top 5 table)."""
    parts_run = [
        ("R1", 12, "3", "May 18, 2026"),
        ("R2", 10, "4", "May 17, 2026"),
        ("R3", 8, "5", "May 10, 2026"),
        ("R4", 2, "1", "May 1, 2026"),
        ("R5", 1, "—", "April 20, 2026"),
    ]
    parts_reg = [
        ("G1", 8, "7", "April 15, 2026"),
        ("G2", 6, "10", "March 3, 2026"),
        ("G3", 4, "14", "February 2, 2026"),
        ("G4", 2, "2", "January 10, 2026"),
        ("G5", 1, "—", "January 5, 2026"),
    ]
    p = sample_thank_you_top_parts()
    return [
        ("🏃 Running Parts", 25, 25, parts_run),
        ("🔁 Regular Parts", 18, 18, parts_reg),
        ("📅 Occasional Parts", 14, 14, p),
        ("👋 Stranger Parts", 9, 9, p),
        ("🆕 New Parts", 4, 4, p),
    ]


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


def test_median_gap_days_consecutive() -> None:
    assert _median_gap_days_consecutive([date(2026, 1, 1)]) is None
    assert _median_gap_days_consecutive([date(2026, 1, 1), date(2026, 1, 11)]) == 10.0
    # Same calendar day repeated (many FIR rows one dispatch) → use distinct days only
    assert _median_gap_days_consecutive(
        [date(2026, 1, 1), date(2026, 1, 1), date(2026, 1, 1), date(2026, 1, 11)]
    ) == 10.0
    # gaps 5 and 10 -> median 7.5
    assert _median_gap_days_consecutive(
        [date(2026, 1, 1), date(2026, 1, 6), date(2026, 1, 16)]
    ) == 7.5


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
        top_parts=sample_thank_you_top_parts(),
        minutes_per_report=15,
    )
    assert "Performance Summary" in subject
    assert "Acme" in body
    assert "Till date, your organization has generated **100 inspection reports**" in body
    assert "Total Active Users in Workspace: **3**" in body
    assert "25.0 hours" in body  # 100 * 15 / 60
    assert "Top 5 Most Frequently Generated Parts Till Date" in body
    assert "Reports Generated in May" not in body
    assert "Assuming each inspection report takes approximately" in body
    assert "Median Gap (Days)" in body
    assert "Last Dispatched Date" in body
    assert body.count("+") >= 6  # mysql-style borders
    assert "| 1    | P1          | 40                | 7                 | May 15, 2026         |" in body


def test_thank_you_send_body_requires_category() -> None:
    from pydantic import ValidationError

    from app.schemas import AdminSubscriptionReminderSendBody

    with pytest.raises(ValidationError):
        AdminSubscriptionReminderSendBody(reminder_type="thank_you")
    with pytest.raises(ValidationError):
        AdminSubscriptionReminderSendBody(reminder_type="ending_soon", thank_you_category="running")
    b = AdminSubscriptionReminderSendBody(reminder_type="thank_you", thank_you_category="new")
    assert b.thank_you_category == "new"
    b_all = AdminSubscriptionReminderSendBody(reminder_type="thank_you", thank_you_category="all")
    assert b_all.thank_you_category == "all"


def test_thank_you_all_category_performance_email() -> None:
    parts = sample_thank_you_top_parts()
    sections = sample_thank_you_all_engagement_sections()
    subject, body, hours_saved = build_admin_thank_you_all_email(
        customer_name="Acme",
        total_report_count=100,
        top_parts_overall=parts,
        engagement_sections=sections,
    )
    assert subject == "Thank You & Performance Summary"
    assert "Dear Acme" in body
    assert "📊 Lifetime Metrics" in body
    assert "Total FIR Reports Generated: 100" in body
    assert "16.7 hours" in body  # 100 * 10 / 60, rounded
    assert hours_saved == 16.7
    assert "₹8,333" in body
    assert "🏆 Overall Top 5 Most Frequently Generated Parts" in body
    assert "Part Engagement Category Summaries" in body
    for title in (
        "🏃 Running Parts",
        "🔁 Regular Parts",
        "📅 Occasional Parts",
        "👋 Stranger Parts",
        "🆕 New Parts",
    ):
        assert title in body
    assert body.count("Top 5 Parts\n") == 5
    assert "| R1          |" in body and "| G1          |" in body


def test_thank_you_tone_varies_by_category() -> None:
    base = dict(
        customer_name="Acme",
        plan_name="Enterprise",
        subscription_start_date="May 1, 2026",
        subscription_end_date="June 18, 2026",
        total_report_count=10,
        workspace_user_count=2,
        top_parts=sample_thank_you_top_parts(),
    )
    _, running, _, _ = build_admin_thank_you_email(category="running", **base)
    _, stranger, _, _ = build_admin_thank_you_email(category="stranger", **base)
    assert "cumulative impact" in running
    assert "ready to reconnect" in stranger.lower()


def test_fir_workspace_requires_trial_or_subscription() -> None:
    c = _company_expired_trial()
    assert can_access_fir_workspace(c, enable_subscription=True, today=date(2026, 3, 1)) is False
