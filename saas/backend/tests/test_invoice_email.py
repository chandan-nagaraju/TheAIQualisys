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
            "invoice_date": "2026-09-22",
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
    assert body.startswith("Dear Customer,")
    assert "Payment Invoice INV-00003" in body
    assert "subscription with TheAIQualisys for the month of September 2026" in body
    assert "- Invoice Amount: INR 5,662.82" in body
    assert "- Billing Cycle: Monthly" in body
    assert "- Subscription Period: 22-Sep-2026 to 22-Oct-2026" in body
    assert "accounting and records" in body
    assert "Regards,\nTeam TheAIQualisys" in body
    assert "CC:" not in body
    html = sent["html"]
    assert "<strong>Payment Invoice INV-00003</strong>" in html
    assert "<strong>Team TheAIQualisys</strong>" in html
    assert sent["subject"] == "Payment Invoice INV-00003 — TheAIQualisys"


def test_resend_invoice_mail_attaches_pdf_bytes(monkeypatch):
    import base64
    import json

    captured: dict = {}

    class _Resp:
        def read(self):
            return b"{}"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def _urlopen(req, timeout=30):
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", _urlopen)
    from app.email_util import send_email_with_pdf_attachment

    pdf = b"%PDF-1.4 invoice"
    send_email_with_pdf_attachment(
        SimpleNamespace(resend_api_key="rk_test", email_from="billing@theaiqualisys.com"),
        to_email="accounts@acme.test",
        cc=["cfo@acme.test"],
        subject="Payment Invoice INV-00003 — TheAIQualisys",
        text="Dear Customer,\n",
        html="<p>Dear Customer,</p>",
        filename="INV-00003.pdf",
        pdf_bytes=pdf,
    )
    payload = captured["payload"]
    assert payload["to"] == ["accounts@acme.test"]
    assert payload["cc"] == ["cfo@acme.test"]
    att = payload["attachments"][0]
    assert att["filename"] == "INV-00003.pdf"
    assert att["content_type"] == "application/pdf"
    assert base64.b64decode(att["content"]) == pdf


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
