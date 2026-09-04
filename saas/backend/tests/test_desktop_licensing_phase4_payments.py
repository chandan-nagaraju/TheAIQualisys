"""Phase 4: UPI payment submit, admin approve/reject, license minting."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException

from app.config import Settings
from app.licensing.constants import (
    LICENSE_STATUS_ISSUED,
    ORDER_STATUS_APPROVED,
    ORDER_STATUS_PENDING_PAYMENT,
    ORDER_STATUS_PAYMENT_SUBMITTED,
    PAYMENT_STATUS_APPROVED,
    PAYMENT_STATUS_PENDING_REVIEW,
    PAYMENT_STATUS_REJECTED,
)
from app.licensing.models import DesktopLicense, DesktopOrder, DesktopPayment, DesktopUpiSettings
from app.licensing.payments import (
    approve_payment_and_mint_licenses,
    get_or_create_upi_settings,
    reject_payment,
    serialize_upi_settings,
    submit_payment_for_order,
    update_upi_settings,
)
from app.licensing.service import create_paid_licenses_for_seats


def _fernet_settings() -> Settings:
    return Settings(
        enable_desktop_licensing=True,
        license_key_encryption_secret=Fernet.generate_key().decode(),
    )


def test_upi_settings_create_and_update():
    db = MagicMock()
    db.get.return_value = None
    settings = Settings(upi_id="demo@upi")
    row = get_or_create_upi_settings(db, settings)
    assert row.id == 1
    assert row.upi_id == "demo@upi"
    db.add.assert_called()

    existing = DesktopUpiSettings(id=1, upi_id="old@upi", payee_name="Old")
    db.get.return_value = existing
    admin = SimpleNamespace(id=9)
    updated = update_upi_settings(
        db, admin=admin, upi_id="new@upi", payee_name="Payee", instructions="Pay now"
    )
    assert updated.upi_id == "new@upi"
    assert updated.payee_name == "Payee"
    assert updated.updated_by_admin_id == 9
    ser = serialize_upi_settings(updated)
    assert ser["upi_id"] == "new@upi"


def test_upi_update_requires_fields():
    db = MagicMock()
    db.get.return_value = DesktopUpiSettings(id=1, upi_id="x", payee_name="y")
    with pytest.raises(HTTPException) as exc:
        update_upi_settings(db, admin=SimpleNamespace(id=1), upi_id="", payee_name="A", instructions=None)
    assert exc.value.status_code == 400


def test_submit_payment_requires_utr():
    db = MagicMock()
    with pytest.raises(HTTPException) as exc:
        submit_payment_for_order(
            db,
            _fernet_settings(),
            user=SimpleNamespace(id=1, company_id=1),
            order_id=1,
            utr_reference="",
        )
    assert exc.value.status_code == 400


def test_submit_payment_valid_and_amount_from_order():
    settings = _fernet_settings()
    order = DesktopOrder(
        order_number="TAQ-2026-000001",
        company_id=1,
        user_id=5,
        product_id=1,
        plan_id=1,
        product_code="QR_CODE",
        product_name="QR",
        plan_code="ANNUAL",
        plan_name="Annual",
        duration_days=365,
        seats=2,
        unit_price_inr=1000,
        total_price_inr=2000,
        currency="INR",
        status=ORDER_STATUS_PENDING_PAYMENT,
    )
    order.id = 11
    lock = MagicMock()
    lock.scalar_one_or_none.return_value = order
    pending = MagicMock()
    pending.scalar_one_or_none.return_value = None
    db = MagicMock()
    db.execute.side_effect = [lock, pending]
    db.get.return_value = DesktopUpiSettings(id=1, upi_id="pay@upi", payee_name="Co")

    payment = submit_payment_for_order(
        db,
        settings,
        user=SimpleNamespace(id=5, company_id=1),
        order_id=11,
        utr_reference="ABC123456789",
    )
    assert payment.amount_inr == 2000
    assert payment.status == PAYMENT_STATUS_PENDING_REVIEW
    assert order.status == ORDER_STATUS_PAYMENT_SUBMITTED
    assert payment.reference_note == "ABC123456789"


def test_submit_payment_wrong_user():
    order = DesktopOrder(
        order_number="TAQ-2026-000002",
        company_id=1,
        user_id=99,
        product_id=1,
        plan_id=1,
        product_code="QR_CODE",
        product_name="QR",
        plan_code="A",
        plan_name="A",
        duration_days=365,
        seats=1,
        unit_price_inr=100,
        total_price_inr=100,
        currency="INR",
        status=ORDER_STATUS_PENDING_PAYMENT,
    )
    order.id = 2
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = order
    with pytest.raises(HTTPException) as exc:
        submit_payment_for_order(
            db,
            _fernet_settings(),
            user=SimpleNamespace(id=1, company_id=1),
            order_id=2,
            utr_reference="ABCDEF123456",
        )
    assert exc.value.status_code == 404


def test_reject_requires_reason():
    db = MagicMock()
    payment = DesktopPayment(order_id=1, amount_inr=100, status=PAYMENT_STATUS_PENDING_REVIEW)
    payment.id = 3
    order = DesktopOrder(
        order_number="TAQ-2026-000003",
        company_id=1,
        user_id=1,
        product_id=1,
        plan_id=1,
        product_code="X",
        product_name="X",
        plan_code="Y",
        plan_name="Y",
        duration_days=365,
        seats=1,
        unit_price_inr=100,
        total_price_inr=100,
        currency="INR",
        status=ORDER_STATUS_PAYMENT_SUBMITTED,
    )
    order.id = 1
    pay_lock = MagicMock()
    pay_lock.scalar_one_or_none.return_value = payment
    order_lock = MagicMock()
    order_lock.scalar_one.return_value = order
    db.execute.side_effect = [pay_lock, order_lock]
    with pytest.raises(HTTPException) as exc:
        reject_payment(db, admin=SimpleNamespace(id=1), payment_id=3, reason="no")
    assert exc.value.status_code == 400


def test_reject_creates_no_licenses_and_reopens_order():
    payment = DesktopPayment(order_id=1, amount_inr=100, status=PAYMENT_STATUS_PENDING_REVIEW)
    payment.id = 4
    order = DesktopOrder(
        order_number="TAQ-2026-000004",
        company_id=1,
        user_id=1,
        product_id=1,
        plan_id=1,
        product_code="X",
        product_name="X",
        plan_code="Y",
        plan_name="Y",
        duration_days=365,
        seats=1,
        unit_price_inr=100,
        total_price_inr=100,
        currency="INR",
        status=ORDER_STATUS_PAYMENT_SUBMITTED,
    )
    order.id = 1
    db = MagicMock()
    db.execute.side_effect = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=payment)),
        MagicMock(scalar_one=MagicMock(return_value=order)),
    ]
    reject_payment(db, admin=SimpleNamespace(id=2), payment_id=4, reason="UTR not found in bank statement")
    assert payment.status == PAYMENT_STATUS_REJECTED
    assert payment.review_note.startswith("UTR")
    assert order.status == ORDER_STATUS_PENDING_PAYMENT


def test_mint_one_and_four_seats_unique_keys_unbound():
    settings = _fernet_settings()
    db = MagicMock()
    db.flush = MagicMock()
    minted1 = create_paid_licenses_for_seats(
        db,
        settings,
        product_id=1,
        plan_id=2,
        order_id=10,
        company_id=3,
        licensed_user_id=7,
        seat_count=1,
        duration_days=365,
        created_by_admin_id=1,
    )
    assert len(minted1) == 1
    lic, key = minted1[0]
    assert lic.seat_index == 1
    assert lic.licensed_user_id == 7
    assert lic.product_id == 1
    assert lic.bound_device_id is None
    assert lic.status == LICENSE_STATUS_ISSUED
    assert lic.key_encrypted
    assert key.startswith("AQ-")

    minted4 = create_paid_licenses_for_seats(
        db,
        settings,
        product_id=1,
        plan_id=2,
        order_id=11,
        company_id=3,
        licensed_user_id=7,
        seat_count=4,
        duration_days=365,
        created_by_admin_id=1,
    )
    assert len(minted4) == 4
    keys = [k for _, k in minted4]
    assert len(set(keys)) == 4
    hashes = [row.key_hash for row, _ in minted4]
    assert len(set(hashes)) == 4
    for i, (row, _) in enumerate(minted4, start=1):
        assert row.seat_index == i
        assert row.bound_device_id is None
        assert row.order_id == 11


def test_approve_idempotent_second_call():
    settings = _fernet_settings()
    payment = DesktopPayment(
        order_id=5, amount_inr=4000, status=PAYMENT_STATUS_PENDING_REVIEW, reference_note="UTR123456"
    )
    payment.id = 50
    order = DesktopOrder(
        order_number="TAQ-2026-000050",
        company_id=1,
        user_id=2,
        product_id=1,
        plan_id=1,
        product_code="QR_CODE",
        product_name="QR",
        plan_code="ANNUAL",
        plan_name="Annual",
        duration_days=365,
        seats=4,
        unit_price_inr=1000,
        total_price_inr=4000,
        currency="INR",
        status=ORDER_STATUS_PAYMENT_SUBMITTED,
    )
    order.id = 5
    db = MagicMock()

    def execute(stmt):
        result = MagicMock()
        sql = str(stmt)
        if "desktop_payments" in sql or "DesktopPayment" in sql:
            result.scalar_one_or_none.return_value = payment
            return result
        if "desktop_orders" in sql or "DesktopOrder" in sql:
            result.scalar_one.return_value = order
            return result
        # count licenses
        result.scalar_one.return_value = 0
        return result

    db.execute.side_effect = execute

    with patch("app.licensing.payments.create_paid_licenses_for_seats") as mint:
        fake_lic = DesktopLicense(
            product_id=1,
            plan_id=1,
            order_id=5,
            company_id=1,
            licensed_user_id=2,
            entitlement_type="paid",
            seat_index=1,
            key_prefix="AQ",
            key_last4="ABCD",
            key_hash="h" * 64,
            key_encrypted="c",
            status=LICENSE_STATUS_ISSUED,
        )
        fake_lic.id = 1
        mint.return_value = [(fake_lic, "AQ-TEST-KEY")] * 4
        # Fix: return 4 distinct
        mint.return_value = [(fake_lic, f"KEY-{i}") for i in range(4)]
        payment_out, order_out, licenses = approve_payment_and_mint_licenses(
            db, settings, admin=SimpleNamespace(id=1), payment_id=50
        )
        assert payment_out.status == PAYMENT_STATUS_APPROVED
        assert order_out.status == ORDER_STATUS_APPROVED
        assert len(licenses) == 4
        assert mint.call_count == 1

    # Second approval: already approved
    payment.status = PAYMENT_STATUS_APPROVED
    order.status = ORDER_STATUS_APPROVED
    with pytest.raises(HTTPException) as exc:
        approve_payment_and_mint_licenses(db, settings, admin=SimpleNamespace(id=1), payment_id=50)
    assert exc.value.status_code == 409


def test_approve_refuses_when_licenses_already_exist():
    settings = _fernet_settings()
    payment = DesktopPayment(order_id=8, amount_inr=100, status=PAYMENT_STATUS_PENDING_REVIEW)
    payment.id = 80
    order = DesktopOrder(
        order_number="TAQ-2026-000080",
        company_id=1,
        user_id=2,
        product_id=1,
        plan_id=1,
        product_code="QR_CODE",
        product_name="QR",
        plan_code="A",
        plan_name="A",
        duration_days=365,
        seats=1,
        unit_price_inr=100,
        total_price_inr=100,
        currency="INR",
        status=ORDER_STATUS_PAYMENT_SUBMITTED,
    )
    order.id = 8
    db = MagicMock()

    def execute(stmt):
        result = MagicMock()
        # payment lock
        if not hasattr(execute, "n"):
            execute.n = 0
        execute.n += 1
        if execute.n == 1:
            result.scalar_one_or_none.return_value = payment
        elif execute.n == 2:
            result.scalar_one.return_value = order
        else:
            result.scalar_one.return_value = 1  # existing license count
        return result

    db.execute.side_effect = execute
    with pytest.raises(HTTPException) as exc:
        approve_payment_and_mint_licenses(db, settings, admin=SimpleNamespace(id=1), payment_id=80)
    assert exc.value.status_code == 409


def test_feature_flag_off_payment_routes(monkeypatch):
    from fastapi.testclient import TestClient

    import app.licensing.feature_flag as ff
    from app.main import create_app

    monkeypatch.setattr(ff, "get_settings", lambda: Settings(enable_desktop_licensing=False))
    app = create_app()
    app.state.startup_complete = True
    app.state.startup_status = "ok"
    client = TestClient(app)
    assert client.get("/api/desktop/upi-settings").status_code == 404
    assert client.post("/api/admin/desktop/payment-requests/1/approve", json={}).status_code == 404
    assert client.get("/api/admin/desktop/payment-requests").status_code == 404


def test_migration_035_constraints():
    from pathlib import Path

    sql = (Path(__file__).resolve().parents[1] / "migrations" / "035_desktop_payment_and_mint.sql").read_text()
    assert "desktop_upi_settings" in sql
    assert "uq_desktop_licenses_order_seat" in sql
    assert "pending_review" in sql
