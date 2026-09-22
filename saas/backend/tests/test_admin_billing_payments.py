"""Platform Admin SaaS billing payments: list, quote, submit, verify, reject."""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.billing_payments import (
    STATUS_PENDING,
    STATUS_REJECTED,
    STATUS_VERIFIED,
    get_billing_payment,
    list_billing_payments,
    reject_payment,
    serialize_billing_payment,
    submit_payment_done,
    verify_payment,
    billing_payment_counts,
)
from app.schemas import AdminBillingPaymentListResponse
from app.billing_period import billing_total_inr, normalize_billing_period, period_length_days, subscription_end_from_start
from app.models import BillingPayment, Company, CompanyUser


def _payment(**kwargs) -> BillingPayment:
    row = BillingPayment(
        company_id=kwargs.get("company_id", 1),
        user_id=kwargs.get("user_id", 2),
        plan_name=kwargs.get("plan_name", "Enterprise"),
        amount_inr=kwargs.get("amount_inr", 6799),
        payment_method="UPI",
        reference_note=kwargs.get("reference_note", "PAY-00009"),
        payment_date=kwargs.get("payment_date", datetime(2026, 9, 21, 10, 0, tzinfo=timezone.utc)),
        status=kwargs.get("status", STATUS_PENDING),
        module_key="fir",
        module_label="FIR",
        plan_type="enterprise",
        billing_period="MONTHLY",
        subscription_duration="1 Month",
        currency="INR",
        pricing_snapshot={"monthly_price": 6799, "plan": "Enterprise"},
        payment_code="PAY-00009",
        payment_submitted_at=datetime(2026, 9, 20, 16, 20, tzinfo=timezone.utc),
        customer_name_snapshot="Priya",
        company_name_snapshot="Acme Tools",
        email_snapshot="ops@acme.test",
    )
    row.id = kwargs.get("id", 9)
    company = Company(
        company_name="Acme Tools",
        vendor_code="ACM",
        plan_type="pro",
        subscription_status="trial",
        subscription_start=date(2026, 9, 1),
        subscription_end=date(2026, 10, 1),
    )
    company.id = 1
    user = CompanyUser(company_id=1, email="ops@acme.test", password_hash="x", name="Priya")
    user.id = 2
    company.users = [user]
    row.company = company
    row.user = user
    return row


def test_billing_period_aliases():
    assert normalize_billing_period("1m") == "MONTHLY"
    assert normalize_billing_period("monthly") == "MONTHLY"
    assert normalize_billing_period("3m") == "QUARTERLY"
    assert billing_total_inr(6799, "MONTHLY", enterprise=True) == 6799
    assert period_length_days("MONTHLY") == 30
    assert period_length_days("QUARTERLY") == 90
    assert period_length_days("HALF_YEARLY") == 180
    assert period_length_days("YEARLY") == 365
    assert subscription_end_from_start(date(2026, 9, 21), "MONTHLY") == date(2026, 10, 21)
    assert subscription_end_from_start(date(2026, 9, 21), "QUARTERLY") == date(2026, 12, 20)


def test_admin_billing_payments_routes_include_optional_trailing_slash():
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "app" / "routers" / "admin.py").read_text(encoding="utf-8")
    assert '@router.get("/billing/payments"' in src
    assert '@router.get("/billing/payments/"' in src
    assert src.count('@router.get("/notifications"') >= 1
    assert '@router.get("/notifications/"' not in src


def test_billing_payment_counts_empty_list_payload():
    db = MagicMock()
    db.execute.return_value.all.return_value = []
    counts = billing_payment_counts(db)
    payload = AdminBillingPaymentListResponse(
        pending_count=counts[STATUS_PENDING],
        verified_count=counts[STATUS_VERIFIED],
        rejected_count=counts[STATUS_REJECTED],
        items=[],
    )
    assert payload.model_dump() == {
        "pending_count": 0,
        "verified_count": 0,
        "rejected_count": 0,
        "items": [],
    }
    assert counts["pending"] == 0


def test_serialize_billing_payment_joins_company_and_user():
    out = serialize_billing_payment(_payment(), settings=SimpleNamespace(whatsapp_number="917892007580"))
    assert out["id"] == 9
    assert out["payment_code"] == "PAY-00009"
    assert out["customer_name"] == "Priya"
    assert out["company_name"] == "Acme Tools"
    assert out["email"] == "ops@acme.test"
    assert out["module_label"] == "FIR"
    assert out["billing_period"] == "MONTHLY"
    assert out["amount_inr"] == 6799
    assert out["status"] == STATUS_PENDING
    assert out["subscription_start"] is None
    assert out["subscription_end"] is None
    assert out["payment_verified_at"] is None
    assert out["whatsapp_number"] == "917892007580"


def test_list_billing_payments_rejects_unknown_status():
    db = MagicMock()
    with pytest.raises(HTTPException) as exc:
        list_billing_payments(db, status_filter="approved")
    assert exc.value.status_code == 400


def test_list_billing_payments_filters_pending():
    pending = _payment(id=1, status=STATUS_PENDING)
    db = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [pending]
    db.execute.return_value = result
    rows = list_billing_payments(db, status_filter=STATUS_PENDING)
    assert len(rows) == 1
    assert rows[0].status == STATUS_PENDING


def test_get_billing_payment_404():
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = None
    with pytest.raises(HTTPException) as exc:
        get_billing_payment(db, 99)
    assert exc.value.status_code == 404


def test_submit_reuses_pending_duplicate():
    existing = _payment()
    db = MagicMock()
    # quote_payment -> resolve catalog
    fir_row = SimpleNamespace(
        fir_plan_type="enterprise",
        display_name="Enterprise",
        monthly_price=6799,
        yearly_price=None,
        id=3,
    )
    first = MagicMock()
    first.scalars.return_value.all.return_value = [fir_row]
    second = MagicMock()
    second.scalars.return_value.first.return_value = existing
    third = MagicMock()
    third.scalar_one_or_none.return_value = 1
    db.execute.side_effect = [first, second, third]
    user = CompanyUser(company_id=1, email="ops@acme.test", password_hash="x", name="Priya")
    user.id = 2
    company = Company(company_name="Acme Tools", vendor_code="ACM", plan_type="enterprise", subscription_status="trial")
    company.id = 1
    row, already = submit_payment_done(
        db, user=user, company=company, module_key="fir", plan_type="enterprise", billing_period_raw="MONTHLY"
    )
    assert already is True
    assert row.id == 9
    db.add.assert_not_called()


def test_verify_sets_dates_from_admin_verification_not_submit(monkeypatch):
    submitted = datetime(2026, 9, 20, 16, 20, tzinfo=timezone.utc)
    verified = datetime(2026, 9, 21, 17, 45, tzinfo=timezone.utc)
    monkeypatch.setattr("app.billing_payments._utc_now", lambda: verified)
    row = _payment(status=STATUS_PENDING)
    row.payment_submitted_at = submitted
    row.payment_date = submitted
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = row
    admin = SimpleNamespace(id=4)
    out = verify_payment(db, admin=admin, payment_id=9)
    assert out.status == STATUS_VERIFIED
    assert out.verified_by_admin_id == 4
    assert out.verified_at == verified
    assert out.payment_submitted_at == submitted
    assert out.billing_period == "MONTHLY"
    assert out.subscription_duration == "1 Month"
    assert out.subscription_start_date == date(2026, 9, 21)
    assert out.subscription_end_date == date(2026, 10, 21)
    payload = serialize_billing_payment(out)
    assert payload["payment_submitted_at"].startswith("2026-09-20")
    assert payload["payment_verified_at"].startswith("2026-09-21T17:45")
    assert payload["subscription_start"] == "2026-09-21"
    assert payload["subscription_end"] == "2026-10-21"
    assert payload["subscription_start_date"] == "2026-09-21"
    assert payload["subscription_end_date"] == "2026-10-21"
    assert out.company.subscription_start == date(2026, 9, 21)
    assert out.company.subscription_end == date(2026, 10, 21)
    assert out.company.subscription_status == "active"
    assert out.company.plan_type == "enterprise"
    assert out.payment_submitted_at == submitted


def test_verify_rejects_already_verified_without_recalculating():
    row = _payment(status=STATUS_VERIFIED)
    row.verified_at = datetime(2026, 9, 21, 17, 45, tzinfo=timezone.utc)
    row.subscription_start_date = date(2026, 9, 21)
    row.subscription_end_date = date(2026, 10, 21)
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = row
    with pytest.raises(HTTPException) as exc:
        verify_payment(db, admin=SimpleNamespace(id=4), payment_id=9)
    assert exc.value.status_code == 409
    assert row.subscription_start_date == date(2026, 9, 21)
    assert row.subscription_end_date == date(2026, 10, 21)
    assert row.verified_at == datetime(2026, 9, 21, 17, 45, tzinfo=timezone.utc)


def test_reject_requires_reason():
    row = _payment(status=STATUS_PENDING)
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = row
    with pytest.raises(HTTPException) as exc:
        reject_payment(db, admin=SimpleNamespace(id=1), payment_id=9, reason="nope")
    assert exc.value.status_code == 400
    out = reject_payment(db, admin=SimpleNamespace(id=1), payment_id=9, reason="incorrect_amount")
    assert out.status == STATUS_REJECTED
    assert out.rejection_reason == "incorrect_amount"


def test_verify_persists_monthly_dates_and_keeps_submitted_at(monkeypatch):
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    submitted = datetime(2026, 9, 20, 16, 20, tzinfo=timezone.utc)
    verified = datetime(2026, 9, 21, 17, 45, tzinfo=timezone.utc)
    monkeypatch.setattr("app.billing_payments._utc_now", lambda: verified)

    engine = create_engine("sqlite:///:memory:")
    Company.__table__.create(engine)
    BillingPayment.__table__.create(engine)
    with Session(engine) as db:
        company = Company(
            id=1,
            company_name="Acme Tools",
            vendor_code="ACM",
            plan_type="pro",
            subscription_status="trial",
            subscription_start=date(2026, 9, 12),
            subscription_end=date(2026, 10, 12),
        )
        db.add(company)
        row = BillingPayment(
            company_id=1,
            user_id=2,
            plan_name="Enterprise",
            amount_inr=6799,
            payment_method="UPI",
            payment_date=submitted,
            status=STATUS_PENDING,
            plan_type="enterprise",
            billing_period="MONTHLY",
            subscription_duration="1 Month",
            payment_submitted_at=submitted,
        )
        db.add(row)
        db.flush()
        payment_id = row.id
        monkeypatch.setattr("app.billing_payments.get_billing_payment", lambda _db, _id: _db.get(BillingPayment, payment_id))
        verify_payment(db, admin=SimpleNamespace(id=4), payment_id=payment_id)
        db.commit()

    with Session(engine) as db:
        stored = db.execute(select(BillingPayment).where(BillingPayment.id == payment_id)).scalar_one()
        company = db.get(Company, 1)
        assert stored.status == STATUS_VERIFIED
        assert stored.payment_submitted_at.replace(tzinfo=timezone.utc) == submitted
        assert stored.verified_at.replace(tzinfo=timezone.utc) == verified
        assert stored.subscription_start_date == date(2026, 9, 21)
        assert stored.subscription_end_date == date(2026, 10, 21)
        assert stored.billing_period == "MONTHLY"
        assert stored.subscription_duration == "1 Month"
        assert stored.subscription_start_date.isoformat() == "2026-09-21"
        assert stored.subscription_end_date.isoformat() == "2026-10-21"
        assert company.subscription_start == date(2026, 9, 21)
        assert company.subscription_end == date(2026, 10, 21)
        assert company.subscription_status == "active"
        assert company.plan_type == "enterprise"
        with pytest.raises(HTTPException) as exc:
            verify_payment(db, admin=SimpleNamespace(id=4), payment_id=payment_id)
        assert exc.value.status_code == 409
        assert stored.subscription_start_date == date(2026, 9, 21)
        assert stored.subscription_end_date == date(2026, 10, 21)
        assert company.subscription_start == date(2026, 9, 21)
        assert company.subscription_end == date(2026, 10, 21)
        assert stored.verified_at.replace(tzinfo=timezone.utc) == verified
        assert stored.payment_submitted_at.replace(tzinfo=timezone.utc) == submitted

