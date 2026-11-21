"""Phase 1 corrective tests: encryption policy + 1:1:1 binding enforcement."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet

from app.config import Settings
from app.licensing.binding import (
    LicenseBindingError,
    activate_license_on_device,
    admin_reset_device_binding,
    assert_device_binding_allowed,
    assert_license_user_product,
    get_active_activation,
)
from app.licensing.constants import (
    ACTIVATION_STATUS_ACTIVE,
    ACTIVATION_STATUS_DEACTIVATED,
    LICENSE_STATUS_ACTIVE,
    LICENSE_STATUS_ISSUED,
)
from app.licensing.keys import (
    LicenseKeyEncryptionError,
    decrypt_license_key,
    encrypt_license_key,
    fernet_from_secret,
    generate_license_key,
    require_valid_encryption_secret,
)
from app.licensing.models import DesktopActivation, DesktopDevice, DesktopLicense, DesktopProduct
from app.licensing.service import mint_license_key_material


def _valid_fernet_secret() -> str:
    return Fernet.generate_key().decode()


def test_valid_fernet_secret_accepted():
    secret = _valid_fernet_secret()
    assert require_valid_encryption_secret(secret) == secret
    f = fernet_from_secret(secret)
    key = generate_license_key()
    ct = encrypt_license_key(key, secret)
    assert decrypt_license_key(ct, secret) is not None


def test_missing_encryption_secret_rejected():
    with pytest.raises(LicenseKeyEncryptionError):
        require_valid_encryption_secret(None)
    with pytest.raises(LicenseKeyEncryptionError):
        require_valid_encryption_secret("")
    with pytest.raises(LicenseKeyEncryptionError):
        fernet_from_secret(None)


def test_weak_passphrase_secret_rejected():
    with pytest.raises(LicenseKeyEncryptionError):
        require_valid_encryption_secret("phase1-test-secret")
    with pytest.raises(LicenseKeyEncryptionError):
        encrypt_license_key(generate_license_key(), "not-a-fernet-key")


def test_mint_requires_valid_fernet_secret():
    with pytest.raises(LicenseKeyEncryptionError):
        mint_license_key_material(Settings(license_key_encryption_secret=None))
    with pytest.raises(LicenseKeyEncryptionError):
        mint_license_key_material(Settings(license_key_encryption_secret="weak-passphrase"))
    secret = _valid_fernet_secret()
    material = mint_license_key_material(Settings(license_key_encryption_secret=secret))
    assert material.key_encrypted
    assert decrypt_license_key(material.key_encrypted, secret) is not None


def test_wrong_user_rejected():
    lic = SimpleNamespace(licensed_user_id=10, product_id=1)
    with pytest.raises(LicenseBindingError) as exc:
        assert_license_user_product(lic, website_user_id=99, product_id=1)
    assert exc.value.code == "wrong_user"


def test_wrong_product_rejected():
    lic = SimpleNamespace(licensed_user_id=10, product_id=1)
    with pytest.raises(LicenseBindingError) as exc:
        assert_license_user_product(lic, website_user_id=10, product_id=2)
    assert exc.value.code == "wrong_product"


def test_two_active_devices_rejected():
    lic = SimpleNamespace(bound_device_id=1)
    device_b = SimpleNamespace(id=2)
    active_on_a = SimpleNamespace(device_id=1, status=ACTIVATION_STATUS_ACTIVE)
    with pytest.raises(LicenseBindingError) as exc:
        assert_device_binding_allowed(lic, device=device_b, active_activation=active_on_a)
    assert exc.value.code == "device_bound"


def test_inactive_historical_then_new_device_allowed():
    """After admin reset: bound_device cleared, only deactivated history → new device OK."""
    lic = SimpleNamespace(bound_device_id=None)
    device_b = SimpleNamespace(id=2)
    # No active activation (historical deactivated rows are ignored by get_active_activation)
    assert_device_binding_allowed(lic, device=device_b, active_activation=None)


def test_same_device_reactivation_allowed():
    lic = SimpleNamespace(bound_device_id=7)
    device = SimpleNamespace(id=7)
    active = SimpleNamespace(device_id=7, status=ACTIVATION_STATUS_ACTIVE)
    assert_device_binding_allowed(lic, device=device, active_activation=active)


def _mock_db_for_activate(*, license_row, product, device=None, active=None):
    """Minimal Session mock for activate_license_on_device."""
    db = MagicMock()

    def execute(stmt):
        result = MagicMock()
        # with_for_update lock path / get_active_activation / get device
        sql = str(stmt)
        if "desktop_licenses" in sql or getattr(stmt, "column_descriptions", None):
            pass
        # Use call order heuristics via side_effect list instead
        return result

    # Simpler: patch helpers used inside activate
    return db


def test_activate_valid_same_user_product_device(monkeypatch):
    lic = DesktopLicense(
        product_id=1,
        company_id=1,
        licensed_user_id=42,
        entitlement_type="paid",
        key_prefix="AQ",
        key_last4="ZZZZ",
        key_hash="a" * 64,
        key_encrypted="x",
        status=LICENSE_STATUS_ISSUED,
    )
    lic.id = 100
    product = DesktopProduct(code="QR_CODE", name="QR", listing_active=1)
    product.id = 1
    device = DesktopDevice(fingerprint_hash="fp-aaa")
    device.id = 5

    db = MagicMock()
    lock_result = MagicMock()
    lock_result.scalar_one.return_value = lic
    active_result = MagicMock()
    active_result.scalar_one_or_none.return_value = None

    # First execute: lock license; later executes for active + device lookup
    db.execute.side_effect = [lock_result, active_result]
    db.get.return_value = product

    monkeypatch.setattr(
        "app.licensing.binding.get_or_create_device",
        lambda *a, **k: device,
    )
    monkeypatch.setattr(
        "app.licensing.binding.get_active_activation",
        lambda *a, **k: None,
    )

    result = activate_license_on_device(
        db,
        license_row=lic,
        website_user_id=42,
        product_id=1,
        fingerprint_hash="fp-aaa",
    )
    assert result.created_new_activation is True
    assert result.license.bound_device_id == 5
    assert result.license.status == LICENSE_STATUS_ACTIVE
    assert result.activation.status == ACTIVATION_STATUS_ACTIVE
    db.add.assert_called()
    db.flush.assert_called()


def test_activate_rejects_wrong_user(monkeypatch):
    lic = DesktopLicense(
        product_id=1,
        company_id=1,
        licensed_user_id=42,
        entitlement_type="paid",
        key_prefix="AQ",
        key_last4="ZZZZ",
        key_hash="b" * 64,
        key_encrypted="x",
        status=LICENSE_STATUS_ISSUED,
    )
    lic.id = 101
    db = MagicMock()
    lock_result = MagicMock()
    lock_result.scalar_one.return_value = lic
    db.execute.return_value = lock_result

    with pytest.raises(LicenseBindingError) as exc:
        activate_license_on_device(
            db,
            license_row=lic,
            website_user_id=999,
            product_id=1,
            fingerprint_hash="fp",
        )
    assert exc.value.code == "wrong_user"


def test_activate_rejects_second_device_while_active(monkeypatch):
    lic = DesktopLicense(
        product_id=1,
        company_id=1,
        licensed_user_id=42,
        entitlement_type="paid",
        key_prefix="AQ",
        key_last4="ZZZZ",
        key_hash="c" * 64,
        key_encrypted="x",
        status=LICENSE_STATUS_ACTIVE,
        bound_device_id=1,
    )
    lic.id = 102
    product = DesktopProduct(code="QR_CODE", name="QR", listing_active=1)
    product.id = 1
    device_b = DesktopDevice(fingerprint_hash="fp-bbb")
    device_b.id = 2
    active_a = DesktopActivation(
        license_id=102,
        user_id=42,
        device_id=1,
        status=ACTIVATION_STATUS_ACTIVE,
    )

    db = MagicMock()
    lock_result = MagicMock()
    lock_result.scalar_one.return_value = lic
    db.execute.return_value = lock_result
    db.get.return_value = product

    monkeypatch.setattr("app.licensing.binding.get_or_create_device", lambda *a, **k: device_b)
    monkeypatch.setattr("app.licensing.binding.get_active_activation", lambda *a, **k: active_a)

    with pytest.raises(LicenseBindingError) as exc:
        activate_license_on_device(
            db,
            license_row=lic,
            website_user_id=42,
            product_id=1,
            fingerprint_hash="fp-bbb",
        )
    assert exc.value.code == "device_bound"


def test_activate_after_reset_allows_new_device(monkeypatch):
    lic = DesktopLicense(
        product_id=1,
        company_id=1,
        licensed_user_id=42,
        entitlement_type="paid",
        key_prefix="AQ",
        key_last4="ZZZZ",
        key_hash="d" * 64,
        key_encrypted="x",
        status=LICENSE_STATUS_ISSUED,
        bound_device_id=None,
    )
    lic.id = 103
    product = DesktopProduct(code="QR_CODE", name="QR", listing_active=1)
    product.id = 1
    device_b = DesktopDevice(fingerprint_hash="fp-new")
    device_b.id = 9

    db = MagicMock()
    lock_result = MagicMock()
    lock_result.scalar_one.return_value = lic
    db.execute.return_value = lock_result
    db.get.return_value = product

    monkeypatch.setattr("app.licensing.binding.get_or_create_device", lambda *a, **k: device_b)
    # Historical deactivated activation exists but get_active_activation returns None
    monkeypatch.setattr("app.licensing.binding.get_active_activation", lambda *a, **k: None)
    monkeypatch.setattr("app.licensing.binding.get_activation_for_license_device", lambda *a, **k: None)

    result = activate_license_on_device(
        db,
        license_row=lic,
        website_user_id=42,
        product_id=1,
        fingerprint_hash="fp-new",
    )
    assert result.created_new_activation is True
    assert result.device.id == 9


def test_admin_reset_clears_binding():
    lic = DesktopLicense(
        product_id=1,
        company_id=1,
        licensed_user_id=42,
        entitlement_type="paid",
        key_prefix="AQ",
        key_last4="ZZZZ",
        key_hash="e" * 64,
        key_encrypted="x",
        status=LICENSE_STATUS_ACTIVE,
        bound_device_id=3,
    )
    lic.id = 104
    active = DesktopActivation(
        license_id=104,
        user_id=42,
        device_id=3,
        status=ACTIVATION_STATUS_ACTIVE,
    )
    db = MagicMock()
    lock_result = MagicMock()
    lock_result.scalar_one.return_value = lic
    db.execute.return_value = lock_result

    with patch("app.licensing.binding.get_active_activation", return_value=active):
        admin_reset_device_binding(db, license_row=lic, admin_id=1)

    assert active.status == ACTIVATION_STATUS_DEACTIVATED
    assert active.deactivated_at is not None
    assert lic.bound_device_id is None
    assert lic.status == LICENSE_STATUS_ISSUED


def test_migration_033_defines_partial_unique_and_conflict_guard():
    from pathlib import Path

    sql = (Path(__file__).resolve().parents[1] / "migrations" / "033_desktop_licensing_one_active_device.sql").read_text()
    assert "uq_desktop_activations_one_active_per_license" in sql
    assert "WHERE status = 'active'" in sql
    assert "RAISE EXCEPTION" in sql
    assert "No rows were deleted" in sql
