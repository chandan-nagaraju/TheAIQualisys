"""Payment overdue subscription reminder (days overdue + 30th close-all-ties deadline)."""

from datetime import date
from pathlib import Path

from app.dates import payment_overdue_close_date, unpaid_month_count
from app.email_util import build_payment_overdue_email


def test_close_date_is_thirtieth_of_this_month():
    assert payment_overdue_close_date(date(2026, 11, 28)) == date(2026, 11, 30)
    assert payment_overdue_close_date(date(2026, 11, 30)) == date(2026, 11, 30)


def test_close_date_rolls_to_next_month_after_the_30th():
    assert payment_overdue_close_date(date(2026, 12, 1)) == date(2026, 12, 30)
    assert payment_overdue_close_date(date(2026, 2, 28)) == date(2026, 2, 28)


def test_unpaid_months_two_at_november_30_from_october_30():
    assert unpaid_month_count(date(2026, 10, 30), date(2026, 11, 28)) == 1
    assert unpaid_month_count(date(2026, 10, 30), date(2026, 11, 30)) == 2


def test_overdue_email_states_days_pay_link_and_close_ties():
    subject, text, html = build_payment_overdue_email(
        customer_name="Sri Balaji Fabrication Works",
        plan_name="Pro",
        paid_through=date(2026, 10, 30),
        today=date(2026, 11, 28),
        pay_url="https://www.theaiqualisys.com/upgrade",
        gstin="29CCTPC6405L1Z4",
        invoice_number="INV-00012",
    )
    assert subject == "Payment overdue — please settle by November 30, 2026"
    assert "overdue for 29 days" in text
    assert "coverage ended on October 30, 2026" in text
    assert "1 month of payment is currently outstanding" in text
    assert "Pay now: https://www.theaiqualisys.com/upgrade" in text
    assert "previous invoice INV-00012 is attached" in text
    assert "Bank Name: Axis Bank" in text
    assert "Primary Account Holder: Chandan N" in text
    assert "Account Number: 919010044064495" in text
    assert "IFSC Code: UTIB0001204" in text
    assert "Account Type: Savings A/c" in text
    assert "UPI ID: 7892007580@axisbank" in text
    assert "GSTIN: 29CCTPC6405L1Z4" in text
    assert "after November 30, 2026 we will close all ties" in text
    assert "2 months of dues will be outstanding" in text
    assert "overdue for <strong>29 days</strong>" in html
    assert "Pay now" in html
    assert "INV-00012" in html
    assert "7892007580@axisbank" in html
    assert "29CCTPC6405L1Z4" in html
    assert "close all ties" in html


def test_admin_reminder_menu_includes_payment_overdue():
    page = (
        Path(__file__).resolve().parents[2]
        / "frontend"
        / "src"
        / "components"
        / "AdminSubscriptionReminderButton.tsx"
    ).read_text(encoding="utf-8")
    assert 'send("payment_overdue")' in page
    assert "close all ties" in page
    assert "previous invoice attached" in page
    schemas = (Path(__file__).resolve().parents[1] / "app" / "schemas.py").read_text(encoding="utf-8")
    assert '"payment_overdue"' in schemas
    invoices = (Path(__file__).resolve().parents[1] / "app" / "billing_invoices.py").read_text(encoding="utf-8")
    assert "def latest_billing_invoice_for_company" in invoices
