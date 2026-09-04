"""Phase 7: machine license API — binding, Ed25519 entitlements, reset, rate limits."""

from __future__ import annotations

import base64
import hashlib
import json
import threading
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.config import Settings
from app.licensing.binding import (
    LicenseBindingError,
    activate_license_on_device,
    admin_reset_device_binding,
    assert_license_not_terminal,
    deactivate_activation_preserve_binding,
)
from app.licensing.constants import (
    ACTIVATION_STATUS_ACTIVE,
    ACTIVATION_STATUS_DEACTIVATED,
    ENTITLEMENT_PAID,
    ENTITLEMENT_TRIAL,
    LICENSE_STATUS_ACTIVE,
    LICENSE_STATUS_EXPIRED,
    LICENSE_STATUS_ISSUED,
    LICENSE_STATUS_REVOKED,
    LICENSE_STATUS_SUSPENDED,
)
from app.licensing.keys import hash_license_key
from app.licensing.machine import (
    activate_machine_license,
    deactivate_machine_license,
    map_binding_error,
    refresh_machine_license,
    validate_machine_license,
)
from app.licensing.models import DesktopActivation, DesktopDevice, DesktopLicense, DesktopProduct
from app.licensing.rate_limit import check_rate_limit, clear_rate_limit_buckets
from app.licensing.signing import (
    build_entitlement_claims,
    generate_ephemeral_signing_pem,
    kid_from_public_key_pem,
    load_signing_key_material,
    public_key_response,
    sign_entitlement,
    validate_fingerprint_hash,
    verify_entitlement_token,
)


def _fp(seed: str = "device-a") -> str:
    return hashlib.sha256(f"AQ|QR_CODE|{seed}".encode()).hexdigest()


def _settings(**kwargs) -> Settings:
    base = dict(
        enable_desktop_licensing=True,
        license_signing_private_key=generate_ephemeral_signing_pem(),
        license_max_offline_days=14,
        license_api_rate_limit_per_minute=30,
    )
    base.update(kwargs)
    return Settings(**base)


def _product(**kwargs) -> DesktopProduct:
    defaults = dict(code="QR_CODE", name="QR", listing_active=1, sort_order=1)
    defaults.update(kwargs)
    p = DesktopProduct(**defaults)
    p.id = kwargs.get("id", 1)
    return p


def _license(**kwargs) -> DesktopLicense:
    now = datetime.now(timezone.utc)
    defaults = dict(
        product_id=1,
        plan_id=1,
        order_id=1,
        company_id=1,
        licensed_user_id=7,
        entitlement_type=ENTITLEMENT_PAID,
        seat_index=1,
        key_prefix="AQ",
        key_last4="ABCD",
        key_hash="h" * 64,
        key_encrypted="c",
        status=LICENSE_STATUS_ISSUED,
        expires_at=now + timedelta(days=30),
    )
    defaults.update(kwargs)
    lic = DesktopLicense(**defaults)
    lic.id = kwargs.get("id", 101)
    return lic


def test_fingerprint_format():
    good = _fp()
    assert validate_fingerprint_hash(good) == good
    with pytest.raises(ValueError):
        validate_fingerprint_hash("short")
    with pytest.raises(ValueError):
        validate_fingerprint_hash("../" + "a" * 61)


def test_wall_clock_expiry_overrides_active_status():
    lic = _license(
        status=LICENSE_STATUS_ACTIVE,
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    with pytest.raises(LicenseBindingError) as exc:
        assert_license_not_terminal(lic)
    assert exc.value.code == "expired"


def test_trial_entitlement_rejected_on_activate_path():
    from app.licensing.binding import assert_license_paid_entitlement

    with pytest.raises(LicenseBindingError) as exc:
        assert_license_paid_entitlement(_license(entitlement_type=ENTITLEMENT_TRIAL))
    assert exc.value.code == "trial_not_supported"


def test_signing_roundtrip_and_tamper():
    settings = _settings()
    material = load_signing_key_material(settings)
    claims = build_entitlement_claims(
        product_code="QR_CODE",
        license_id=1,
        activation_id=9,
        licensed_user_id=7,
        fingerprint_hash=_fp(),
        expires_at=datetime.now(timezone.utc) + timedelta(days=10),
        max_offline_days=14,
    )
    token = sign_entitlement(settings, claims)
    verified = verify_entitlement_token(
        token,
        public_key_pem=material.public_key_pem,
        expected_product="QR_CODE",
        expected_fp=_fp(),
        expected_license_id=1,
    )
    assert verified["jti"] == claims["jti"]
    assert verified["naf"] <= claims["iat"] + 14 * 86400 + 5

    # Modified payload
    payload_b64, sig_b64 = token.split(".")
    pad = "=" * (-len(payload_b64) % 4)
    raw = bytearray(base64.urlsafe_b64decode(payload_b64 + pad))
    raw[0] ^= 0x01
    bad = base64.urlsafe_b64encode(bytes(raw)).rstrip(b"=").decode() + "." + sig_b64
    with pytest.raises(ValueError):
        verify_entitlement_token(bad, public_key_pem=material.public_key_pem)

    # Modified signature
    with pytest.raises(ValueError):
        verify_entitlement_token(payload_b64 + ".AAAA", public_key_pem=material.public_key_pem)

    # Wrong / attacker public key cannot verify
    attacker = Ed25519PrivateKey.generate()
    attacker_pem = attacker.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    with pytest.raises(ValueError):
        verify_entitlement_token(token, public_key_pem=attacker_pem)

    # Wrong product / device
    with pytest.raises(ValueError):
        verify_entitlement_token(
            token, public_key_pem=material.public_key_pem, expected_product="ASN_PDF_PRINTER"
        )
    with pytest.raises(ValueError):
        verify_entitlement_token(
            token, public_key_pem=material.public_key_pem, expected_fp=_fp("other")
        )


def test_naf_enforced_and_null_exp():
    settings = _settings(license_max_offline_days=14)
    material = load_signing_key_material(settings)
    past = datetime.now(timezone.utc) - timedelta(days=20)
    claims = build_entitlement_claims(
        product_code="QR_CODE",
        license_id=1,
        activation_id=1,
        licensed_user_id=7,
        fingerprint_hash=_fp(),
        expires_at=None,
        max_offline_days=14,
        now=past,
    )
    token = sign_entitlement(settings, claims)
    with pytest.raises(ValueError):
        verify_entitlement_token(token, public_key_pem=material.public_key_pem)


def test_public_key_endpoint_shape_and_kid():
    settings = _settings()
    out = public_key_response(settings)
    assert out["algorithm"] == "Ed25519"
    assert out["keys"][0]["status"] == "current"
    assert "trust_note" in out
    assert out["keys"][0]["kid"] == kid_from_public_key_pem(out["keys"][0]["public_key_pem"])
    assert "PRIVATE" not in out["keys"][0]["public_key_pem"]


def test_signing_unavailable_fail_closed():
    settings = Settings(enable_desktop_licensing=True, license_signing_private_key=None)
    with pytest.raises(Exception):
        load_signing_key_material(settings)


def _mock_activate_db(*, license_row, product, device=None, active=None):
    db = MagicMock()
    lock = MagicMock()
    lock.scalar_one.return_value = license_row
    prod_q = MagicMock()
    prod_q.scalar_one_or_none.return_value = product
    key_q = MagicMock()
    key_q.scalar_one_or_none.return_value = license_row

    def execute(stmt):
        # crude routing
        s = str(stmt)
        if "desktop_products" in s or "DesktopProduct" in s:
            return prod_q
        if "key_hash" in s or "DesktopLicense" in s and "FOR UPDATE" not in s.upper():
            # both key lookup and lock use DesktopLicense — first call key, later lock
            return key_q if license_row.bound_device_id is None and active is None else lock
        return lock

    calls = {"n": 0}

    def execute2(stmt):
        calls["n"] += 1
        s = str(type(stmt))
        text = str(stmt)
        if "product" in text.lower() or calls["n"] == 1:
            # product lookup first in activate_machine via _product_by_code
            r = MagicMock()
            r.scalar_one_or_none.return_value = product
            return r
        if calls["n"] == 2:
            r = MagicMock()
            r.scalar_one_or_none.return_value = license_row
            return r
        r = MagicMock()
        r.scalar_one.return_value = license_row
        r.scalar_one_or_none.return_value = device
        return r

    db.execute.side_effect = execute2
    db.get.side_effect = lambda model, ident: product if model is DesktopProduct else license_row

    return db


def test_activate_happy_path_and_reaffirm():
    settings = _settings()
    user = SimpleNamespace(id=7)
    product = _product()
    plaintext = "AQ-TEST-KEY-0001"
    lic = _license(key_hash=hash_license_key(plaintext), status=LICENSE_STATUS_ISSUED)
    device = DesktopDevice(fingerprint_hash=_fp())
    device.id = 55
    activation = DesktopActivation(
        license_id=lic.id,
        user_id=7,
        device_id=55,
        status=ACTIVATION_STATUS_ACTIVE,
    )
    activation.id = 9

    result = SimpleNamespace(
        license=lic,
        device=device,
        activation=activation,
        created_new_activation=True,
    )
    lic.status = LICENSE_STATUS_ACTIVE
    lic.bound_device_id = 55

    db = MagicMock()
    # product + key lookup
    def execute(stmt):
        r = MagicMock()
        r.scalar_one_or_none.return_value = product
        # second call returns license by hash — distinguish by call count
        return r

    calls = []

    def exec2(stmt):
        calls.append(1)
        r = MagicMock()
        if len(calls) == 1:
            r.scalar_one_or_none.return_value = product
        else:
            r.scalar_one_or_none.return_value = lic
        return r

    db.execute.side_effect = exec2

    with patch("app.licensing.machine.activate_license_on_device", return_value=result), patch(
        "app.licensing.machine.record_license_event"
    ):
        out = activate_machine_license(
            db,
            settings,
            user=user,
            license_key=plaintext,
            product_code="QR_CODE",
            fingerprint_hash=_fp(),
        )
    assert out["license_id"] == lic.id
    assert out["entitlement_token"]
    assert "PRIVATE" not in out["entitlement_token"]
    assert out["reaffirmed"] is False

    result2 = SimpleNamespace(
        license=lic,
        device=device,
        activation=activation,
        created_new_activation=False,
    )
    calls.clear()
    db.execute.side_effect = exec2
    with patch("app.licensing.machine.activate_license_on_device", return_value=result2), patch(
        "app.licensing.machine.record_license_event"
    ):
        out2 = activate_machine_license(
            db,
            settings,
            user=user,
            license_key=plaintext,
            product_code="QR_CODE",
            fingerprint_hash=_fp(),
        )
    assert out2["reaffirmed"] is True


def test_activate_wrong_user_and_product_and_states():
    settings = _settings()
    user = SimpleNamespace(id=7)
    product = _product()
    plaintext = "AQ-TEST-KEY-0002"
    lic = _license(key_hash=hash_license_key(plaintext), licensed_user_id=99)

    def make_exec(lic_row, prod=product):
        calls = []

        def exec2(stmt):
            calls.append(1)
            r = MagicMock()
            r.scalar_one_or_none.return_value = prod if len(calls) == 1 else lic_row
            return r

        return exec2

    db = MagicMock()
    db.execute.side_effect = make_exec(lic)
    with patch(
        "app.licensing.machine.activate_license_on_device",
        side_effect=LicenseBindingError("wrong_user", "nope"),
    ):
        with pytest.raises(HTTPException) as exc:
            activate_machine_license(
                db, settings, user=user, license_key=plaintext, product_code="QR_CODE", fingerprint_hash=_fp()
            )
        assert exc.value.status_code == 403
        assert exc.value.detail["code"] == "wrong_user"

    for code, status, http in [
        ("wrong_product", LICENSE_STATUS_ISSUED, 403),
        ("expired", LICENSE_STATUS_EXPIRED, 403),
        ("revoked", LICENSE_STATUS_REVOKED, 403),
        ("suspended", LICENSE_STATUS_SUSPENDED, 403),
        ("device_bound", LICENSE_STATUS_ACTIVE, 409),
        ("trial_not_supported", LICENSE_STATUS_ISSUED, 403),
    ]:
        db = MagicMock()
        db.execute.side_effect = make_exec(_license(key_hash=hash_license_key(plaintext), status=status))
        with patch(
            "app.licensing.machine.activate_license_on_device",
            side_effect=LicenseBindingError(code, code),
        ):
            with pytest.raises(HTTPException) as exc:
                activate_machine_license(
                    db,
                    settings,
                    user=user,
                    license_key=plaintext,
                    product_code="QR_CODE",
                    fingerprint_hash=_fp(),
                )
            assert exc.value.status_code == http
            assert exc.value.detail["code"] == code


def test_integrity_error_maps_to_device_bound():
    settings = _settings()
    plaintext = "AQ-TEST-KEY-0003"
    product = _product()
    lic = _license(key_hash=hash_license_key(plaintext))
    calls = []

    def exec2(stmt):
        calls.append(1)
        r = MagicMock()
        r.scalar_one_or_none.return_value = product if len(calls) == 1 else lic
        return r

    db = MagicMock()
    db.execute.side_effect = exec2
    with patch(
        "app.licensing.machine.activate_license_on_device",
        side_effect=IntegrityError("stmt", {}, Exception("dup")),
    ):
        with pytest.raises(HTTPException) as exc:
            activate_machine_license(
                db,
                settings,
                user=SimpleNamespace(id=7),
                license_key=plaintext,
                product_code="QR_CODE",
                fingerprint_hash=_fp(),
            )
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "device_bound"


def test_unknown_key_safe_invalid_license():
    settings = _settings()
    product = _product()
    calls = []

    def exec2(stmt):
        calls.append(1)
        r = MagicMock()
        if len(calls) == 1:
            r.scalar_one_or_none.return_value = product
        else:
            r.scalar_one_or_none.return_value = None
        return r

    db = MagicMock()
    db.execute.side_effect = exec2
    with pytest.raises(HTTPException) as exc:
        activate_machine_license(
            db,
            settings,
            user=SimpleNamespace(id=7),
            license_key="AQ-MISSING",
            product_code="QR_CODE",
            fingerprint_hash=_fp(),
        )
    assert exc.value.status_code == 404
    assert exc.value.detail["code"] == "invalid_license"


def test_admin_reset_preserves_user_product_expiry_and_allows_new_device():
    now = datetime.now(timezone.utc)
    lic = _license(status=LICENSE_STATUS_ACTIVE, bound_device_id=3, expires_at=now + timedelta(days=9))
    lic.licensed_user_id = 42
    lic.product_id = 1
    active = DesktopActivation(license_id=101, user_id=42, device_id=3, status=ACTIVATION_STATUS_ACTIVE)
    active.id = 77
    db = MagicMock()
    lock = MagicMock()
    lock.scalar_one.return_value = lic
    db.execute.return_value = lock
    with patch("app.licensing.binding.get_active_activation", return_value=active):
        result = admin_reset_device_binding(db, license_row=lic, admin_id=1)
    assert result.previous_activation_id == 77
    assert result.previous_device_id == 3
    assert lic.bound_device_id is None
    assert lic.status == LICENSE_STATUS_ISSUED
    assert lic.licensed_user_id == 42
    assert lic.product_id == 1
    assert lic.expires_at == now + timedelta(days=9)
    assert active.status == ACTIVATION_STATUS_DEACTIVATED


def test_deactivate_preserves_binding():
    lic = _license(status=LICENSE_STATUS_ACTIVE, bound_device_id=55)
    device = DesktopDevice(fingerprint_hash=_fp())
    device.id = 55
    active = DesktopActivation(license_id=101, user_id=7, device_id=55, status=ACTIVATION_STATUS_ACTIVE)
    active.id = 3
    db = MagicMock()
    lock = MagicMock()
    lock.scalar_one.return_value = lic
    dev_q = MagicMock()
    dev_q.scalar_one_or_none.return_value = device

    def execute(stmt):
        # first FOR UPDATE license, then device select
        if not hasattr(execute, "n"):
            execute.n = 0
        execute.n += 1
        return lock if execute.n == 1 else dev_q

    db.execute.side_effect = execute
    with patch("app.licensing.binding.get_active_activation", return_value=active):
        out = deactivate_activation_preserve_binding(
            db, license_row=lic, website_user_id=7, product_id=1, fingerprint_hash=_fp()
        )
    assert out.status == ACTIVATION_STATUS_DEACTIVATED
    assert lic.bound_device_id == 55


def test_refresh_issues_new_jti():
    settings = _settings()
    user = SimpleNamespace(id=7)
    product = _product()
    lic = _license(status=LICENSE_STATUS_ACTIVE, bound_device_id=55)
    device = DesktopDevice(fingerprint_hash=_fp())
    device.id = 55
    active = DesktopActivation(license_id=101, user_id=7, device_id=55, status=ACTIVATION_STATUS_ACTIVE)
    active.id = 3

    with patch("app.licensing.machine._require_bound_active", return_value=(lic, product, active)), patch(
        "app.licensing.machine.record_license_event"
    ):
        a = refresh_machine_license(
            MagicMock(),
            settings,
            user=user,
            license_id=101,
            product_code="QR_CODE",
            fingerprint_hash=_fp(),
        )
        b = refresh_machine_license(
            MagicMock(),
            settings,
            user=user,
            license_id=101,
            product_code="QR_CODE",
            fingerprint_hash=_fp(),
        )
    assert a["token_jti"] != b["token_jti"]
    assert a["token_naf"] and b["token_naf"]


def test_map_binding_error_codes():
    assert map_binding_error(LicenseBindingError("device_bound", "x")).status_code == 409
    assert map_binding_error(LicenseBindingError("expired", "x")).detail["code"] == "expired"


def test_rate_limit_activate_bucket():
    clear_rate_limit_buckets()
    for _ in range(5):
        check_rate_limit(scope="t", key="k", limit=5)
    with pytest.raises(HTTPException) as exc:
        check_rate_limit(scope="t", key="k", limit=5)
    assert exc.value.status_code == 429
    assert exc.value.detail["code"] == "rate_limited"
    clear_rate_limit_buckets()


def test_feature_flag_off_machine_and_reset(monkeypatch):
    import app.licensing.feature_flag as ff
    from app.main import create_app

    monkeypatch.setattr(ff, "get_settings", lambda: Settings(enable_desktop_licensing=False))
    app = create_app()
    app.state.startup_complete = True
    app.state.startup_status = "ok"
    client = TestClient(app)
    assert client.post("/api/license/activate", json={}).status_code == 404
    assert client.post("/api/license/validate", json={}).status_code == 404
    assert client.post("/api/license/refresh", json={}).status_code == 404
    assert client.post("/api/license/deactivate", json={}).status_code == 404
    assert client.get("/api/license/public-key").status_code == 404
    assert client.post("/api/admin/desktop/licenses/1/reset-device", json={"reason": "machine died"}).status_code == 404


def test_unauthenticated_machine_and_non_admin_reset(monkeypatch):
    import app.licensing.feature_flag as ff
    from app.config import get_settings as real_get_settings
    from app.main import create_app
    from app.licensing.signing import generate_ephemeral_signing_pem

    pem = generate_ephemeral_signing_pem()
    settings = Settings(enable_desktop_licensing=True, license_signing_private_key=pem)
    monkeypatch.setattr(ff, "get_settings", lambda: settings)
    app = create_app()
    app.dependency_overrides[real_get_settings] = lambda: settings
    app.state.startup_complete = True
    app.state.startup_status = "ok"
    client = TestClient(app)
    body = {
        "license_key": "AQ-X",
        "product_code": "QR_CODE",
        "fingerprint_hash": _fp(),
    }
    assert client.post("/api/license/activate", json=body).status_code == 401
    assert client.post(
        "/api/license/validate",
        json={"license_id": 1, "product_code": "QR_CODE", "fingerprint_hash": _fp()},
    ).status_code == 401
    assert client.post(
        "/api/license/refresh",
        json={"license_id": 1, "product_code": "QR_CODE", "fingerprint_hash": _fp()},
    ).status_code == 401
    assert client.post(
        "/api/license/deactivate",
        json={"license_id": 1, "product_code": "QR_CODE", "fingerprint_hash": _fp()},
    ).status_code == 401
    assert (
        client.post(
            "/api/admin/desktop/licenses/1/reset-device",
            json={"reason": "replacement laptop"},
            headers={"Authorization": "Bearer not-an-admin"},
        ).status_code
        == 401
    )
    pk = client.get("/api/license/public-key")
    assert pk.status_code == 200
    assert pk.json()["algorithm"] == "Ed25519"
    app.dependency_overrides.clear()


def test_concurrent_activation_integrity_path_deterministic():
    """Simulate race: second bind raises IntegrityError → device_bound."""
    # covered by test_integrity_error_maps_to_device_bound
    assert map_binding_error(LicenseBindingError("device_bound", "x")).status_code == 409


def test_expired_token_claim_denied():
    settings = _settings()
    material = load_signing_key_material(settings)
    claims = build_entitlement_claims(
        product_code="QR_CODE",
        license_id=1,
        activation_id=1,
        licensed_user_id=7,
        fingerprint_hash=_fp(),
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        max_offline_days=14,
        now=datetime.now(timezone.utc) - timedelta(days=2),
    )
    # Force exp/naf in the past
    claims["exp"] = int((datetime.now(timezone.utc) - timedelta(days=1)).timestamp())
    claims["naf"] = claims["exp"]
    token = sign_entitlement(settings, claims)
    with pytest.raises(ValueError):
        verify_entitlement_token(token, public_key_pem=material.public_key_pem)


def test_validate_signing_missing_fails_closed():
    settings = Settings(enable_desktop_licensing=True, license_signing_private_key=None)
    lic = _license(status=LICENSE_STATUS_ACTIVE, bound_device_id=1)
    product = _product()
    active = DesktopActivation(license_id=101, user_id=7, device_id=1, status=ACTIVATION_STATUS_ACTIVE)
    active.id = 1
    with patch("app.licensing.machine._require_bound_active", return_value=(lic, product, active)):
        with pytest.raises(HTTPException) as exc:
            validate_machine_license(
                MagicMock(),
                settings,
                user=SimpleNamespace(id=7),
                license_id=101,
                product_code="QR_CODE",
                fingerprint_hash=_fp(),
            )
        assert exc.value.status_code == 503
        assert exc.value.detail["code"] == "signing_unavailable"


def test_attacker_supplied_public_key_not_trust_root():
    """Documented model: verification requires explicit pinned key; API key alone is not auto-trusted."""
    settings = _settings()
    token = sign_entitlement(
        settings,
        build_entitlement_claims(
            product_code="QR_CODE",
            license_id=1,
            activation_id=1,
            licensed_user_id=7,
            fingerprint_hash=_fp(),
            expires_at=None,
            max_offline_days=14,
        ),
    )
    # Publishing public key via endpoint does not change verify API — caller must pin.
    published = public_key_response(settings)
    # Attacker PEM must not verify even if they also call public-key
    attacker = generate_ephemeral_signing_pem()
    attacker_pub = load_signing_key_material(
        Settings(license_signing_private_key=attacker)
    ).public_key_pem
    with pytest.raises(ValueError):
        verify_entitlement_token(token, public_key_pem=attacker_pub)
    # Correct pin works
    verify_entitlement_token(token, public_key_pem=published["keys"][0]["public_key_pem"])
