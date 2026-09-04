"""Unit tests for desktop licensing Phase 1 foundation (no DB required)."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.config import Settings
from app.licensing.constants import DESKTOP_PRODUCT_CODES, ENTITLEMENT_PAID, PHASE_FOUNDATION
from app.licensing.feature_flag import is_desktop_licensing_enabled, require_desktop_licensing_enabled
from app.licensing.keys import (
    decrypt_license_key,
    encrypt_license_key,
    generate_license_key,
    hash_license_key,
    mask_license_key,
    normalize_license_key,
    verify_license_key,
)
from app.licensing.service import mint_license_key_material, product_code_is_known


def test_generate_license_key_format():
    key = generate_license_key()
    parts = key.split("-")
    assert parts[0] == "AQ"
    assert len(parts) == 5
    assert all(len(p) == 4 for p in parts[1:])
    # Ambiguous chars excluded
    assert "0" not in key and "1" not in key and "O" not in key and "I" not in key


def test_hash_normalize_verify_roundtrip():
    key = generate_license_key()
    h = hash_license_key(key)
    assert len(h) == 64
    assert verify_license_key(key, h)
    assert verify_license_key(key.lower(), h)
    assert not verify_license_key(generate_license_key(), h)


def test_normalize_strips_noise():
    assert normalize_license_key("  aq-abcd-efgh-ijkl-mnop  ") == "AQ-ABCD-EFGH-IJKL-MNOP"


def test_encrypt_decrypt_with_passphrase():
    key = generate_license_key()
    secret = "dev-only-passphrase-not-for-production"
    ct = encrypt_license_key(key, secret)
    assert ct is not None
    assert decrypt_license_key(ct, secret) == normalize_license_key(key)
    assert decrypt_license_key(ct, "wrong-secret") is None
    assert encrypt_license_key(key, None) is None


def test_mask_license_key():
    key = "AQ-ABCD-EFGH-IJKL-MNOP"
    masked = mask_license_key(key)
    assert masked.startswith("AQ-")
    assert masked.endswith("MNOP")
    assert "ABCD" not in masked


def test_mint_material_includes_hash_and_optional_cipher():
    settings = Settings(license_key_encryption_secret="phase1-test-secret")
    material = mint_license_key_material(settings)
    assert verify_license_key(material.plaintext, material.key_hash)
    assert material.key_encrypted is not None
    assert material.key_masked != material.plaintext
    assert "****" in material.key_masked


def test_mint_material_without_encryption_secret():
    settings = Settings(license_key_encryption_secret=None)
    material = mint_license_key_material(settings)
    assert material.key_encrypted is None
    assert len(material.key_hash) == 64


def test_product_codes():
    assert len(DESKTOP_PRODUCT_CODES) == 3
    assert product_code_is_known("QR_CODE")
    assert product_code_is_known("asn_pdf_printer")
    assert not product_code_is_known("FIR")


def test_feature_flag_default_off(monkeypatch):
    from app.config import get_settings
    import app.licensing.feature_flag as ff

    get_settings.cache_clear()
    monkeypatch.setenv("ENABLE_DESKTOP_LICENSING", "false")
    get_settings.cache_clear()
    # Ensure cached settings reflect off
    monkeypatch.setattr(ff, "get_settings", lambda: Settings(enable_desktop_licensing=False))
    assert is_desktop_licensing_enabled() is False
    with pytest.raises(HTTPException) as exc:
        require_desktop_licensing_enabled()
    assert exc.value.status_code == 404


def test_feature_flag_on(monkeypatch):
    import app.licensing.feature_flag as ff

    monkeypatch.setattr(ff, "get_settings", lambda: Settings(enable_desktop_licensing=True))
    assert is_desktop_licensing_enabled() is True
    require_desktop_licensing_enabled()  # no raise


def test_machine_router_stubs_when_enabled(monkeypatch):
    from fastapi.testclient import TestClient

    import app.licensing.feature_flag as ff
    from app.main import create_app

    monkeypatch.setattr(ff, "get_settings", lambda: Settings(enable_desktop_licensing=True))
    app = create_app()
    app.state.startup_complete = True
    app.state.startup_status = "ok"
    client = TestClient(app)
    r = client.post("/api/license/activate", json={})
    assert r.status_code == 501
    assert r.json()["phase"] == PHASE_FOUNDATION
    r2 = client.get("/api/license/public-key")
    assert r2.status_code == 501


def test_machine_router_hidden_when_disabled(monkeypatch):
    from fastapi.testclient import TestClient

    import app.licensing.feature_flag as ff
    from app.main import create_app

    monkeypatch.setattr(ff, "get_settings", lambda: Settings(enable_desktop_licensing=False))
    app = create_app()
    app.state.startup_complete = True
    app.state.startup_status = "ok"
    client = TestClient(app)
    assert client.post("/api/license/activate", json={}).status_code == 404
    assert client.get("/api/license/public-key").status_code == 404


def test_paid_entitlement_constant():
    assert ENTITLEMENT_PAID == "paid"
