"""Phase 5: My Licenses, reveal, email after mint, resend — ownership & key safety."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException

from app.config import Settings
from app.licensing.constants import (
    LICENSE_EMAIL_FAILED,
    LICENSE_EMAIL_PENDING,
    LICENSE_EMAIL_SENT,
    LICENSE_STATUS_ISSUED,
)
from app.licensing.customer_licenses import (
    attempt_send_license_email_for_order,
    build_license_email_body,
    ensure_email_delivery_pending,
    get_owned_license,
    list_licenses_for_user,
    masked_key_from_parts,
    reveal_license_key_for_user,
    serialize_license_public,
)
from app.licensing.keys import encrypt_license_key, hash_license_key
from app.licensing.models import DesktopLicense, DesktopLicenseEmailDelivery, DesktopOrder
from app.licensing.service import create_paid_licenses_for_seats, record_license_event


def _fernet_settings(**kwargs) -> Settings:
    base = dict(
        enable_desktop_licensing=True,
        license_key_encryption_secret=Fernet.generate_key().decode(),
        email_from="noreply@example.com",
        resend_api_key="re_test",
        public_app_url="https://app.example.com",
    )
    base.update(kwargs)
    return Settings(**base)


def _license_row(*, user_id: int = 7, order_id: int = 10, seat: int = 1, settings: Settings | None = None):
    settings = settings or _fernet_settings()
    plaintext = "AQ-TEST-KEY1-KEY2-ABCD"
    lic = DesktopLicense(
        product_id=1,
        plan_id=2,
        order_id=order_id,
        company_id=3,
        licensed_user_id=user_id,
        entitlement_type="paid",
        seat_index=seat,
        key_prefix="AQ",
        key_last4="ABCD",
        key_hash=hash_license_key(plaintext),
        key_encrypted=encrypt_license_key(plaintext, settings.license_key_encryption_secret),
        status=LICENSE_STATUS_ISSUED,
    )
    lic.id = 100 + seat
    lic.bound_device_id = None
    lic.activated_at = None
    lic._plaintext_for_test = plaintext  # type: ignore[attr-defined]
    return lic


def test_list_licenses_only_own_user():
    user = SimpleNamespace(id=7)
    own = _license_row(user_id=7)
    db = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [own]
    db.execute.return_value = result
    rows = list_licenses_for_user(db, user=user)
    assert len(rows) == 1
    assert rows[0].licensed_user_id == 7


def test_get_owned_license_rejects_other_user():
    user = SimpleNamespace(id=7)
    foreign = _license_row(user_id=99)
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = foreign
    db.execute.return_value = result
    with pytest.raises(HTTPException) as exc:
        get_owned_license(db, user=user, license_id=foreign.id)
    assert exc.value.status_code == 404


def test_serialize_license_masked_no_secrets():
    lic = _license_row()
    order = DesktopOrder(
        order_number="TAQ-2026-000001",
        company_id=3,
        user_id=7,
        product_id=1,
        plan_id=2,
        product_code="QR_CODE",
        product_name="QR Code Software",
        plan_code="ANNUAL",
        plan_name="Annual",
        duration_days=365,
        seats=4,
        unit_price_inr=1000,
        total_price_inr=4000,
        currency="INR",
        status="approved",
    )
    out = serialize_license_public(lic, order=order)
    assert "key_encrypted" not in out
    assert "license_key" not in out
    assert "plaintext" not in out
    assert out["key_masked"].startswith("AQ-")
    assert "ABCD" in out["key_masked"]
    assert out["product_name"] == "QR Code Software"
    assert out["plan_name"] == "Annual"
    assert out["seat_index"] == 1
    assert out["is_activated"] is False
    assert out["device_status"] == "Not activated"
    assert out["expires_at"] == (lic.expires_at.isoformat() if lic.expires_at else None)


def test_reveal_own_license_returns_plaintext_only():
    settings = _fernet_settings()
    lic = _license_row(settings=settings)
    user = SimpleNamespace(id=7)
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = lic
    db.execute.return_value = result
    with patch("app.licensing.customer_licenses.record_license_event") as audit:
        key = reveal_license_key_for_user(db, settings, user=user, license_id=lic.id)
        assert key == lic._plaintext_for_test  # type: ignore[attr-defined]
        audit.assert_called()
        meta = audit.call_args.kwargs.get("meta") or {}
        assert "license_key" not in meta
        assert "plaintext" not in str(meta)
        assert "key_encrypted" not in meta


def test_reveal_other_user_rejected():
    settings = _fernet_settings()
    lic = _license_row(user_id=99, settings=settings)
    user = SimpleNamespace(id=7)
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = lic
    db.execute.return_value = result
    with pytest.raises(HTTPException) as exc:
        reveal_license_key_for_user(db, settings, user=user, license_id=lic.id)
    assert exc.value.status_code == 404


def test_reveal_fails_without_encryption_secret():
    settings = Settings(enable_desktop_licensing=True, license_key_encryption_secret=None)
    # Build ciphertext with a real key, then wipe secret for reveal
    good = _fernet_settings()
    lic = _license_row(settings=good)
    user = SimpleNamespace(id=7)
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = lic
    db.execute.return_value = result
    with pytest.raises(HTTPException) as exc:
        reveal_license_key_for_user(db, settings, user=user, license_id=lic.id)
    assert exc.value.status_code == 503


def test_mint_creates_independent_unbound_keys():
    settings = _fernet_settings()
    db = MagicMock()
    minted = create_paid_licenses_for_seats(
        db,
        settings,
        product_id=1,
        plan_id=2,
        order_id=55,
        company_id=3,
        licensed_user_id=7,
        seat_count=4,
        duration_days=365,
    )
    assert len(minted) == 4
    keys = [k for _, k in minted]
    assert len(set(keys)) == 4
    for row, _ in minted:
        assert row.bound_device_id is None
        assert row.status == LICENSE_STATUS_ISSUED
        assert row.licensed_user_id == 7
        assert row.product_id == 1
        assert row.plan_id == 2


def test_email_body_contains_keys_not_secrets():
    order = DesktopOrder(
        order_number="TAQ-2026-000002",
        company_id=1,
        user_id=2,
        product_id=1,
        plan_id=1,
        product_code="QR_CODE",
        product_name="QR Code Software",
        plan_code="ANNUAL",
        plan_name="Annual",
        duration_days=365,
        seats=2,
        unit_price_inr=100,
        total_price_inr=200,
        currency="INR",
        status="approved",
    )
    lic1 = _license_row(seat=1)
    lic2 = _license_row(seat=2)
    subject, body = build_license_email_body(
        customer_name="Ada",
        order=order,
        licenses=[lic1, lic2],
        plaintexts=["AQ-AAAA-BBBB-CCCC-1111", "AQ-AAAA-BBBB-CCCC-2222"],
        my_licenses_url="https://app.example.com/software/licenses",
    )
    assert "QR Code Software" in body
    assert "Annual" in body
    assert "AQ-AAAA-BBBB-CCCC-1111" in body
    assert "software/licenses" in body
    assert "LICENSE_KEY_ENCRYPTION" not in body
    assert "key_encrypted" not in body
    assert "Fernet" not in body
    assert "Ada" in body
    assert "TAQ-2026-000002" in subject


def test_email_failure_does_not_delete_licenses():
    settings = _fernet_settings()
    order = DesktopOrder(
        order_number="TAQ-2026-000003",
        company_id=1,
        user_id=2,
        product_id=1,
        plan_id=1,
        product_code="QR_CODE",
        product_name="QR",
        plan_code="A",
        plan_name="A",
        duration_days=30,
        seats=1,
        unit_price_inr=100,
        total_price_inr=100,
        currency="INR",
        status="approved",
    )
    order.id = 33
    lic = _license_row(order_id=33, settings=settings)
    user = SimpleNamespace(id=2, email="buyer@example.com", name="Buyer", company_id=1)
    delivery = DesktopLicenseEmailDelivery(
        order_id=33,
        company_id=1,
        user_id=2,
        to_email="buyer@example.com",
        status=LICENSE_EMAIL_PENDING,
        attempt_count=0,
    )
    delivery.id = 1

    db = MagicMock()

    def execute(stmt):
        result = MagicMock()
        sql = str(stmt)
        if "desktop_orders" in sql or "DesktopOrder" in sql:
            result.scalar_one_or_none.return_value = order
            return result
        if "desktop_licenses" in sql or "DesktopLicense" in sql:
            result.scalars.return_value.all.return_value = [lic]
            return result
        if "desktop_license_email" in sql or "DesktopLicenseEmailDelivery" in sql:
            result.scalar_one_or_none.return_value = delivery
            return result
        result.scalar_one_or_none.return_value = delivery
        return result

    db.execute.side_effect = execute
    db.get.return_value = user

    with patch("app.licensing.customer_licenses.send_plain_text_email", side_effect=RuntimeError("SMTP down")):
        with patch("app.licensing.customer_licenses.record_license_event"):
            out = attempt_send_license_email_for_order(
                db, settings, order_id=33, actor_type="admin", actor_id=1
            )
    assert out.status == LICENSE_EMAIL_FAILED
    assert out.last_error
    # Licenses untouched — still present
    assert lic.id == 101
    assert lic.status == LICENSE_STATUS_ISSUED


def test_email_retry_does_not_mint():
    settings = _fernet_settings()
    order = DesktopOrder(
        order_number="TAQ-2026-000004",
        company_id=1,
        user_id=2,
        product_id=1,
        plan_id=1,
        product_code="QR_CODE",
        product_name="QR",
        plan_code="A",
        plan_name="A",
        duration_days=30,
        seats=1,
        unit_price_inr=100,
        total_price_inr=100,
        currency="INR",
        status="approved",
    )
    order.id = 44
    lic = _license_row(order_id=44, settings=settings)
    user = SimpleNamespace(id=2, email="buyer@example.com", name="Buyer", company_id=1)
    delivery = DesktopLicenseEmailDelivery(
        order_id=44,
        company_id=1,
        user_id=2,
        to_email="buyer@example.com",
        status=LICENSE_EMAIL_FAILED,
        attempt_count=1,
    )
    delivery.id = 2
    db = MagicMock()

    def execute(stmt):
        result = MagicMock()
        sql = str(stmt)
        if "DesktopOrder" in sql or "desktop_orders" in sql:
            result.scalar_one_or_none.return_value = order
            return result
        if "DesktopLicenseEmailDelivery" in sql or "desktop_license_email" in sql:
            result.scalar_one_or_none.return_value = delivery
            return result
        result.scalars.return_value.all.return_value = [lic]
        return result

    db.execute.side_effect = execute
    db.get.return_value = user

    with patch("app.licensing.customer_licenses.send_plain_text_email") as send:
        with patch("app.licensing.customer_licenses.record_license_event"):
            with patch("app.licensing.service.create_paid_licenses_for_seats") as mint:
                out = attempt_send_license_email_for_order(
                    db,
                    settings,
                    order_id=44,
                    actor_type="user",
                    actor_id=2,
                    is_resend=True,
                    enforce_rate_limit=False,
                )
                mint.assert_not_called()
                send.assert_called_once()
    assert out.status == LICENSE_EMAIL_SENT
    assert out.attempt_count == 2


def test_resend_rate_limit():
    from datetime import datetime, timedelta, timezone

    from app.licensing.customer_licenses import _check_resend_rate

    delivery = DesktopLicenseEmailDelivery(
        order_id=1,
        company_id=1,
        user_id=1,
        to_email="a@b.com",
        status=LICENSE_EMAIL_SENT,
        attempt_count=1,
        last_attempted_at=datetime.now(timezone.utc) - timedelta(seconds=5),
    )
    with pytest.raises(HTTPException) as exc:
        _check_resend_rate(delivery, force_rate_check=True)
    assert exc.value.status_code == 429


def test_ensure_email_delivery_idempotent():
    order = DesktopOrder(
        order_number="X",
        company_id=1,
        user_id=2,
        product_id=1,
        plan_id=1,
        product_code="QR_CODE",
        product_name="QR",
        plan_code="A",
        plan_name="A",
        duration_days=30,
        seats=1,
        unit_price_inr=1,
        total_price_inr=1,
        currency="INR",
        status="approved",
    )
    order.id = 9
    existing = DesktopLicenseEmailDelivery(
        order_id=9, company_id=1, user_id=2, to_email="a@b.com", status=LICENSE_EMAIL_PENDING
    )
    existing.id = 5
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = existing
    db.execute.return_value = result
    user = SimpleNamespace(id=2, email="a@b.com")
    row = ensure_email_delivery_pending(db, order=order, user=user)
    assert row.id == 5
    db.add.assert_not_called()


def test_feature_flag_off_blocks_phase5_routes(monkeypatch):
    from fastapi.testclient import TestClient

    import app.licensing.feature_flag as ff
    from app.main import create_app

    monkeypatch.setattr(ff, "get_settings", lambda: Settings(enable_desktop_licensing=False))
    app = create_app()
    app.state.startup_complete = True
    app.state.startup_status = "ok"
    client = TestClient(app)
    assert client.get("/api/desktop/licenses").status_code == 404
    assert client.post("/api/desktop/licenses/1/reveal").status_code == 404
    assert client.post("/api/desktop/orders/1/resend-license-email").status_code == 404
    assert client.get("/api/admin/desktop/licenses").status_code == 404
    assert client.post("/api/admin/desktop/orders/1/resend-license-email").status_code == 404


def test_unauthenticated_and_company_cannot_use_admin_license_apis(monkeypatch):
    from fastapi.testclient import TestClient

    import app.licensing.feature_flag as ff
    from app.main import create_app

    monkeypatch.setattr(ff, "get_settings", lambda: Settings(enable_desktop_licensing=True))
    app = create_app()
    app.state.startup_complete = True
    app.state.startup_status = "ok"
    client = TestClient(app)
    assert client.get("/api/desktop/licenses").status_code == 401
    assert client.get("/api/admin/desktop/licenses").status_code == 401
    assert client.post("/api/admin/desktop/licenses/1/reveal").status_code == 401
    # Company JWT is not a platform_admin token
    client.headers["Authorization"] = "Bearer not-an-admin-token"
    assert client.get("/api/admin/desktop/licenses").status_code == 401
    assert client.post("/api/admin/desktop/orders/1/resend-license-email").status_code == 401


def test_masked_key_helper():
    assert masked_key_from_parts("AQ", "ZZ99").endswith("ZZ99")
    assert "••••" in masked_key_from_parts("AQ", "ZZ99")


def test_migration_036_email_table():
    from pathlib import Path

    sql = (Path(__file__).resolve().parents[1] / "migrations" / "036_desktop_license_email.sql").read_text()
    assert "desktop_license_email_deliveries" in sql
    assert "pending" in sql
    assert "UNIQUE" in sql.upper() or "unique" in sql


def test_approve_response_schema_excludes_plaintext():
    from app.licensing.schemas import DesktopLicenseMintSummaryOut, DesktopLicenseRevealOut

    summary = DesktopLicenseMintSummaryOut(
        id=1,
        seat_index=1,
        product_id=1,
        status="issued",
        key_prefix="AQ",
        key_last4="ABCD",
        bound_device_id=None,
        expires_at=None,
    )
    data = summary.model_dump()
    assert "license_key" not in data
    assert "key_encrypted" not in data
    reveal = DesktopLicenseRevealOut(
        license_id=1, seat_index=1, license_key="AQ-XXXX", key_masked="AQ-••••ABCD"
    )
    r = reveal.model_dump()
    assert "key_encrypted" not in r
    assert "license_key_encryption_secret" not in r
