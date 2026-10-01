"""SaaS billing invoices generated from verified payments."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.billing_invoices import (
    STATUS_GENERATED,
    TAX_CGST_SGST,
    TAX_IGST,
    _amount_in_words,
    adobe_digital_sign_stamp,
    compute_tax,
    preview_invoice,
    preview_manual_invoice,
    render_invoice_pdf,
)
from app.billing_payments import STATUS_PENDING, STATUS_REJECTED, STATUS_VERIFIED, normalize_payment_method
from app.models import BillingPayment, BillingSettings, Company, CompanyUser


def _settings(**kwargs) -> BillingSettings:
    row = BillingSettings(
        id=1,
        business_name=kwargs.get("business_name", "TheAIQualisys"),
        business_address=kwargs.get("business_address", "Bengaluru"),
        gstin=kwargs.get("gstin", "29AAAAA0000A1Z5"),
        state=kwargs.get("state", "Karnataka"),
        state_code=kwargs.get("state_code", "29"),
        email="billing@example.com",
        phone="9999999999",
        invoice_prefix="INV-",
        cgst_rate=9,
        sgst_rate=9,
        igst_rate=18,
        authorised_signatory_name=kwargs.get("authorised_signatory_name", "Chandan N"),
    )
    return row


def _verified_payment() -> BillingPayment:
    submitted = datetime(2026, 9, 20, 16, 20, tzinfo=timezone.utc)
    verified = datetime(2026, 9, 22, 11, 14, tzinfo=timezone.utc)
    row = BillingPayment(
        company_id=1,
        user_id=2,
        plan_name="Enterprise",
        amount_inr=6799,
        payment_method="UPI",
        reference_note="PAY-00002",
        payment_date=submitted,
        status=STATUS_VERIFIED,
        module_key="fir",
        module_label="FIR",
        plan_type="enterprise",
        billing_period="MONTHLY",
        subscription_duration="1 Month",
        payment_code="PAY-00002",
        payment_submitted_at=submitted,
        verified_at=verified,
        subscription_start_date=date(2026, 9, 22),
        subscription_end_date=date(2026, 10, 22),
        customer_name_snapshot="Sri Balaji fabrication works",
        company_name_snapshot="Sri Balaji fabrication works",
        email_snapshot="ops@example.com",
    )
    row.id = 2
    company = Company(
        company_name="Sri Balaji fabrication works",
        vendor_code="7200465",
        plan_type="enterprise",
        subscription_status="active",
        billing_state="Karnataka",
        billing_state_code="29",
        gstin="29BBBBB0000B1Z5",
        billing_address="Shop 1",
        billing_city="Bengaluru",
        billing_pincode="560001",
        phone="9888888888",
    )
    company.id = 1
    user = CompanyUser(company_id=1, email="ops@example.com", password_hash="x", name="Sri Balaji")
    user.id = 2
    company.users = [user]
    row.company = company
    row.user = user
    row.invoices = []
    return row


def test_gst_intra_state_uses_cgst_sgst():
    settings = _settings()
    tax = compute_tax(taxable=Decimal("6799"), seller_state_code="29", customer_state_code="29", settings=settings)
    assert tax["tax_mode"] == TAX_CGST_SGST
    assert tax["cgst"] == Decimal("611.91")
    assert tax["sgst"] == Decimal("611.91")
    assert tax["igst"] == Decimal("0.00")
    assert tax["grand_total"] == Decimal("8022.82")


def test_gst_inter_state_uses_igst():
    settings = _settings()
    tax = compute_tax(taxable=Decimal("6799"), seller_state_code="29", customer_state_code="33", settings=settings)
    assert tax["tax_mode"] == TAX_IGST
    assert tax["igst"] == Decimal("1223.82")
    assert tax["cgst"] == Decimal("0.00")
    assert tax["grand_total"] == Decimal("8022.82")


def test_preview_rejects_pending_and_rejected():
    db = MagicMock()
    pending = _verified_payment()
    pending.status = STATUS_PENDING
    db.execute.return_value.scalar_one_or_none.return_value = pending
    with pytest.raises(HTTPException) as exc:
        preview_invoice(db, payment_id=2)
    assert exc.value.status_code == 409
    assert "verification" in str(exc.value.detail).lower()

    pending.status = STATUS_REJECTED
    with pytest.raises(HTTPException) as exc2:
        preview_invoice(db, payment_id=2)
    assert exc2.value.status_code == 409


def test_preview_and_pdf_for_pay_00002_monthly(monkeypatch):
    payment = _verified_payment()
    settings = _settings()
    db = MagicMock()

    def _execute(stmt):
        result = MagicMock()
        result.scalar_one_or_none.return_value = payment
        return result

    db.execute.side_effect = _execute
    db.get.return_value = settings
    monkeypatch.setattr("app.billing_invoices.get_billing_payment", lambda _db, _id: payment)
    monkeypatch.setattr("app.billing_invoices.generated_invoice_for_payment", lambda _db, _id: None)
    monkeypatch.setattr("app.billing_invoices.billing_today", lambda: date(2026, 9, 22))
    out = preview_invoice(db, payment_id=2)
    assert out["payment_code"] == "PAY-00002"
    assert out["subscription_start_date"] == "2026-09-22"
    assert out["subscription_end_date"] == "2026-10-22"
    assert out["invoice_date"] == "2026-09-22"
    assert out["taxable_amount"] == 6799.0
    assert out["tax_mode"] == TAX_CGST_SGST
    assert out["vendor_code"] == "7200465"
    assert out["hsn_sac"] == "998314"
    pdf = render_invoice_pdf({**out, "invoice_number": "INV-00001"})
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 400
    raw = pdf.replace(b"\r", b"")
    assert b"/Type /Page" in raw or b"/Type/Page" in raw


def test_preview_blocks_duplicate():
    payment = _verified_payment()
    existing = SimpleNamespace(id=1, invoice_number="INV-00001", status="generated")
    db = MagicMock()
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("app.billing_invoices.get_billing_payment", lambda _db, _id: payment)
    monkeypatch.setattr("app.billing_invoices.generated_invoice_for_payment", lambda _db, _id: existing)
    with pytest.raises(HTTPException) as exc:
        preview_invoice(db, payment_id=2)
    assert exc.value.status_code == 409
    assert "already generated" in str(exc.value.detail).lower()
    monkeypatch.undo()


def test_preview_requires_seller_and_customer_state(monkeypatch):
    payment = _verified_payment()
    payment.company.billing_state_code = None
    settings = _settings()
    db = MagicMock()
    monkeypatch.setattr("app.billing_invoices.get_billing_payment", lambda _db, _id: payment)
    monkeypatch.setattr("app.billing_invoices.generated_invoice_for_payment", lambda _db, _id: None)
    monkeypatch.setattr("app.billing_invoices.get_billing_settings", lambda _db: settings)
    with pytest.raises(HTTPException) as exc:
        preview_invoice(db, payment_id=2)
    assert exc.value.status_code == 400
    assert "customer billing state" in str(exc.value.detail).lower()


def test_preview_gst_inclusive_payment_uses_catalog_taxable(monkeypatch):
    payment = _verified_payment()
    payment.amount_inr = 8022.82
    payment.pricing_snapshot = {"gst_inclusive": True, "taxable_amount_inr": 6799}
    settings = _settings()
    db = MagicMock()
    monkeypatch.setattr("app.billing_invoices.get_billing_payment", lambda _db, _id: payment)
    monkeypatch.setattr("app.billing_invoices.generated_invoice_for_payment", lambda _db, _id: None)
    monkeypatch.setattr("app.billing_invoices.get_billing_settings", lambda _db: settings)
    monkeypatch.setattr("app.billing_invoices.billing_today", lambda: date(2026, 9, 22))
    out = preview_invoice(db, payment_id=2)
    assert out["taxable_amount"] == 6799.0
    assert out["grand_total"] == 8022.82


def test_amount_in_words_matches_gst_invoice_style():
    assert _amount_in_words(Decimal("1484.92")) == (
        "Indian Rupees One Thousand Four Hundred Eighty Four and Ninety Two Paise Only"
    )
    assert _amount_in_words(Decimal("8022.82")).startswith("Indian Rupees Eight Thousand Twenty Two")


def test_normalize_payment_method_bank_modes():
    assert normalize_payment_method("neft") == "NEFT"
    assert normalize_payment_method("RTGS") == "RTGS"
    assert normalize_payment_method("account transfer") == "Account Transfer"
    assert normalize_payment_method("bank transfer") == "Account Transfer"
    with pytest.raises(HTTPException):
        normalize_payment_method("cash")


def _pdf_text_blob(pdf: bytes) -> bytes:
    import re
    import zlib

    parts = [pdf]
    for chunk in re.findall(rb"stream\r?\n(.+?)endstream", pdf, re.S):
        try:
            parts.append(zlib.decompress(chunk))
        except Exception:
            parts.append(chunk)
    return b"\n".join(parts)


def _pdf_tj_joined(pdf: bytes) -> str:
    import re

    chars = re.findall(rb"\(([^)]*)\) Tj", _pdf_text_blob(pdf))
    return b"".join(chars).decode("latin-1", "replace")


def test_preview_can_override_payment_method_to_neft(monkeypatch):
    payment = _verified_payment()
    settings = _settings()
    db = MagicMock()
    monkeypatch.setattr("app.billing_invoices.get_billing_payment", lambda _db, _id: payment)
    monkeypatch.setattr("app.billing_invoices.generated_invoice_for_payment", lambda _db, _id: None)
    monkeypatch.setattr("app.billing_invoices.get_billing_settings", lambda _db: settings)
    monkeypatch.setattr("app.billing_invoices.billing_today", lambda: date(2026, 9, 22))
    out = preview_invoice(db, payment_id=2, payment_method="NEFT")
    assert out["payment_method"] == "NEFT"
    pdf = render_invoice_pdf({
        **out,
        "invoice_number": "INV-00009",
        "seller": {
            **out["seller"],
            "authorised_signatory_name": "Chandan N",
        },
    })
    raw = _pdf_text_blob(pdf)
    assert b"NEFT" in raw
    assert b"Authorised Signatory" in raw
    assert b"Chandan" in raw
    assert b"Digitally signed by Chandan" in raw
    assert b"Date: 2026.09.22" in raw
    assert b"+05'30'" in raw
    joined = _pdf_tj_joined(pdf)
    assert "TheAIQualisys" in joined
    assert "Bangalore-560090" in joined


def test_adobe_digital_sign_stamp_uses_first_name_and_ist():
    stamp = adobe_digital_sign_stamp("Chandan N", datetime(2026, 10, 1, 10, 13, 7, tzinfo=timezone.utc))
    assert stamp["short_name"] == "Chandan"
    assert stamp["by_line"] == "Digitally signed by Chandan"
    assert stamp["date_line"] == "Date: 2026.10.01"
    assert stamp["time_line"] == "15:43:07 +05'30'"


def test_preview_manual_invoice_uses_catalog_and_mode(monkeypatch):
    payment = _verified_payment()
    company = payment.company
    settings = _settings()
    db = MagicMock()
    monkeypatch.setattr("app.billing_invoices._get_company_for_manual_invoice", lambda _db, _id: company)
    monkeypatch.setattr("app.billing_invoices.get_billing_settings", lambda _db: settings)
    monkeypatch.setattr("app.billing_invoices.billing_today", lambda: date(2026, 10, 1))
    monkeypatch.setattr(
        "app.billing_invoices.quote_payment",
        lambda _db, **kwargs: {
            "module_key": "fir",
            "module_label": "FIR",
            "plan_type": "pro",
            "plan_name": "Pro",
            "catalog_id": 2,
            "taxable_amount_inr": 4599,
            "billing_period": "QUARTERLY",
            "billing_period_label": "Quarterly",
            "subscription_duration": "3 Months",
        },
    )
    out = preview_manual_invoice(
        db,
        company_id=1,
        plan_type="pro",
        billing_period="QUARTERLY",
        payment_method="RTGS",
    )
    assert out["payment_method"] == "RTGS"
    assert out["plan_name"] == "Pro"
    assert out["billing_period"] == "QUARTERLY"
    assert out["taxable_amount"] == 4599.0
    assert out["subscription_start_date"] == "2026-10-01"
def test_invoice_pdf_company_seal_rings():
    from pathlib import Path

    page = (
        Path(__file__).resolve().parents[2]
        / "frontend"
        / "src"
        / "pages"
        / "AdminBillingInvoiceDetailPage.tsx"
    ).read_text(encoding="utf-8")
    seal = (Path(__file__).resolve().parents[2] / "frontend" / "src" / "components" / "CompanySeal.tsx").read_text(
        encoding="utf-8"
    )
    assert "CompanySeal" in page
    assert "TheAIQualisys" in seal
    assert "Bangalore-560090" in seal
    assert "name" in seal
    pdf = render_invoice_pdf(
        {
            "invoice_number": "INV-00001",
            "invoice_date": "2026-10-01",
            "company_name": "Acme",
            "grand_total": 100,
            "taxable_amount": 84.75,
            "cgst": 7.63,
            "sgst": 7.63,
            "igst": 0,
            "total_tax": 15.26,
            "tax_mode": "cgst_sgst",
            "seller": {
                "business_name": "TheAIQualisys",
                "authorised_signatory_name": "Chandan N",
            },
            "digitally_signed_at": "2026-10-01T10:52:25+05:30",
        }
    )
    raw = _pdf_text_blob(pdf)
    joined = _pdf_tj_joined(pdf)
    assert "TheAIQualisys" in joined
    assert "Bangalore-560090" in joined
    assert b"Chandan N" in raw
    assert b"Digitally signed by Chandan" in raw

