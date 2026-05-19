"""Billing calendar helpers."""

from datetime import date

from app.dates import billing_month_year_english


def test_billing_month_year_english() -> None:
    assert billing_month_year_english(date(2026, 5, 19)) == "May 2026"
    assert billing_month_year_english(date(2026, 1, 1)) == "January 2026"
