"""Platform Admin SaaS billing payment list (read-only; no verify/reject)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.billing_payments import (
    STATUS_PENDING,
    get_billing_payment,
    list_billing_payments,
    serialize_billing_payment,
)
from app.models import BillingPayment, Company, CompanyUser


def _payment(**kwargs) -> BillingPayment:
    row = BillingPayment(
        company_id=kwargs.get("company_id", 1),
        user_id=kwargs.get("user_id", 2),
        plan_name=kwargs.get("plan_name", "pro"),
        amount_inr=kwargs.get("amount_inr", 1500),
        payment_method=kwargs.get("payment_method", "UPI"),
        reference_note=kwargs.get("reference_note", "UTR123456"),
        payment_date=kwargs.get("payment_date", datetime(2026, 9, 21, 10, 0, tzinfo=timezone.utc)),
        status=kwargs.get("status", STATUS_PENDING),
        proof_path=kwargs.get("proof_path"),
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


def test_serialize_billing_payment_joins_company_and_user():
    out = serialize_billing_payment(_payment())
    assert out["id"] == 9
    assert out["customer_name"] == "Priya"
    assert out["company_name"] == "Acme Tools"
    assert out["email"] == "ops@acme.test"
    assert out["phone"] is None
    assert out["subscription_plan"] == "pro"
    assert out["subscription_start"] == "2026-09-01"
    assert out["amount_inr"] == 1500
    assert out["payment_method"] == "UPI"
    assert out["reference_note"] == "UTR123456"
    assert out["status"] == STATUS_PENDING
    assert out["has_proof"] is False


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
