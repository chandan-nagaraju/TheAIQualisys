"""FIR analytics: financial-year monthly report counts."""

from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.fir_analytics import build_fy_monthly_report_series, fy_april_start_year_for_date


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
