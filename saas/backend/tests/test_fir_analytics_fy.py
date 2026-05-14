"""FIR analytics: financial-year monthly report counts."""

from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.fir_analytics import (
    _median_quantity_from_event_qty_strings,
    _parse_quantity_numeric,
    build_fy_monthly_report_series,
    fy_april_start_year_for_date,
)


def test_fy_april_start_year() -> None:
    assert fy_april_start_year_for_date(date(2026, 3, 31)) == 2025
    assert fy_april_start_year_for_date(date(2026, 4, 1)) == 2026
    assert fy_april_start_year_for_date(date(2026, 5, 7)) == 2026


def test_build_fy_monthly_report_series_buckets() -> None:
    fy0 = 2025
    events = [
        SimpleNamespace(created_at=datetime(2025, 4, 15, 12, 0, tzinfo=timezone.utc)),
        SimpleNamespace(created_at=datetime(2025, 4, 20, 12, 0, tzinfo=timezone.utc)),
        SimpleNamespace(created_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)),
        SimpleNamespace(created_at=datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)),
        SimpleNamespace(created_at=datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)),
    ]
    s = build_fy_monthly_report_series(events, fy0)
    assert len(s) == 12
    assert s[0]["month"] == 4 and s[0]["count"] == 2
    assert s[-1]["month"] == 3 and s[-1]["count"] == 1
    assert sum(m["count"] for m in s) == 3


def test_build_fy_monthly_report_series_invoice_month_vs_logged_month() -> None:
    """Admin Usage counts by created_at; chart uses same so May uploads for April invoices match."""
    fy0 = 2026
    ev = SimpleNamespace(
        invoice_date=date(2026, 4, 15),
        created_at=datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc),
    )
    by_invoice = build_fy_monthly_report_series([ev], fy0, use_invoice_date=True)
    by_logged = build_fy_monthly_report_series([ev], fy0, use_invoice_date=False)
    assert by_invoice[0]["month"] == 4 and by_invoice[0]["count"] == 1 and by_invoice[1]["count"] == 0
    assert by_logged[0]["month"] == 4 and by_logged[0]["count"] == 0 and by_logged[1]["count"] == 1


def test_parse_quantity_numeric_basic() -> None:
    assert _parse_quantity_numeric("10") == 10.0
    assert _parse_quantity_numeric("2.5") == 2.5
    assert _parse_quantity_numeric("1,000") == 1000.0
    assert _parse_quantity_numeric("12 EA") == 12.0
    assert _parse_quantity_numeric("") is None
    assert _parse_quantity_numeric("n/a") is None


def test_median_quantity_from_strings() -> None:
    assert _median_quantity_from_event_qty_strings(["1", "3", "2"]) == 2.0
    assert _median_quantity_from_event_qty_strings(["1", "x", "3"]) == 2.0
    assert _median_quantity_from_event_qty_strings(["1", "2", "3", "4"]) == 2.5
    assert _median_quantity_from_event_qty_strings(["", "bad"]) is None
    assert _median_quantity_from_event_qty_strings(["0", "0.0", ""]) is None
    assert _median_quantity_from_event_qty_strings(["0", "0", "10", "20"]) == 15.0
