"""Email tax invoice to company accounts + CC list."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.billing_invoices import email_invoice
from app.invoice_mail import normalize_cc_emails, normalize_invoice_email
from app.models import Company


def test_normalize_cc_emails_dedupes_and_lowercases():
    assert normalize_invoice_email("Accounts@Firm.IN") == "accounts@firm.in"
    assert normalize_cc_emails(["A@x.com", "a@x.com", "b@x.com"]) == ["a@x.com", "b@x.com"]
    assert normalize_cc_emails("cfo@x.com, ops@x.com") == ["cfo@x.com", "ops@x.com"]
    assert normalize_cc_emails(["accounts@x.com", "cfo@x.com"], exclude="accounts@x.com") == ["cfo@x.com"]
    with pytest.raises(HTTPException):
        normalize_invoice_email("not-an-email")


def test_email_invoice_requires_accounts_address(monkeypatch):
    company = Company(company_name="Acme", vendor_code="ACM", plan_type="pro", subscription_status="active")
    invoice = SimpleNamespace(id=3, invoice_number="INV-00003", company=company, payment=None)
    monkeypatch.setattr("app.billing_invoices.get_billing_invoice", lambda _db, _id: invoice)
    db = MagicMock()
    with pytest.raises(HTTPException) as exc:
        email_invoice(db, 3)
    assert exc.value.status_code == 400
    assert "accounts email" in str(exc.value.detail).lower()


def test_email_invoice_sends_pdf_to_accounts_and_cc(monkeypatch):
    company = Company(
        company_name="Acme",
        vendor_code="ACM",
        plan_type="pro",
        subscription_status="active",
        invoice_accounts_email="accounts@acme.test",
        invoice_cc_emails=["cfo@acme.test", "ops@acme.test"],
    )
    invoice = SimpleNamespace(id=3, invoice_number="INV-00003", company=company, payment=None)
    sent: dict = {}

    def _send(_settings, **kwargs):
        sent.update(kwargs)

    monkeypatch.setattr("app.billing_invoices.get_billing_invoice", lambda _db, _id: invoice)
    monkeypatch.setattr(
        "app.billing_invoices.serialize_billing_invoice",
        lambda _row, db=None: {
            "company_name": "Acme",
            "grand_total": 5662.82,
            "billing_period_label": "Monthly",
            "subscription_start_date": "2026-09-22",
            "subscription_end_date": "2026-10-22",
        },
    )
    monkeypatch.setattr("app.billing_invoices.render_invoice_pdf", lambda _data: b"%PDF-fake")
    monkeypatch.setattr("app.billing_invoices.get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr("app.email_util.is_email_configured", lambda _s: True)
    monkeypatch.setattr("app.email_util.send_email_with_pdf_attachment", _send)

    out = email_invoice(MagicMock(), 3)
    assert out["ok"] is True
    assert out["to"] == "accounts@acme.test"
    assert out["cc"] == ["cfo@acme.test", "ops@acme.test"]
    assert sent["to_email"] == "accounts@acme.test"
    assert sent["cc"] == ["cfo@acme.test", "ops@acme.test"]
    assert sent["filename"] == "INV-00003.pdf"
    assert sent["pdf_bytes"].startswith(b"%PDF")
    body = sent["text"]
    assert body.startswith("Hello,")
    assert "GST tax invoice INV-00003 issued to Acme" in body
    assert "Invoice amount: INR 5,662.82" in body
    assert "Subscription period: Monthly (22-Sep-26 to 22-Oct-26)" in body
    assert "accounts records" in body
    assert "Team,\nTheAIQualisys" in body
    assert "CC:" not in body


def test_email_route_and_mail_fields_exist():
    from pathlib import Path

    admin = (Path(__file__).resolve().parents[1] / "app" / "routers" / "admin.py").read_text(encoding="utf-8")
    detail = (
        Path(__file__).resolve().parents[2]
        / "frontend"
        / "src"
        / "pages"
        / "AdminBillingInvoiceDetailPage.tsx"
    ).read_text(encoding="utf-8")
    mig = (Path(__file__).resolve().parents[1] / "migrations" / "049_company_invoice_emails.sql").read_text()
    assert '@router.post("/billing/invoices/{invoice_id}/email"' in admin
    assert "Email" in detail
    assert "/email" in detail
    assert "invoice_accounts_email" in mig
    assert "invoice_cc_emails" in mig
