"""Phase 6: protected installers / downloads — entitlement, tokens, upload security."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.config import Settings
from app.licensing.constants import (
    ENTITLEMENT_PAID,
    ENTITLEMENT_TRIAL,
    INSTALLER_CHANNEL_ARCHIVED,
    INSTALLER_CHANNEL_CURRENT,
    INSTALLER_CHANNEL_RECOMMENDED,
    LICENSE_STATUS_ACTIVE,
    LICENSE_STATUS_EXPIRED,
    LICENSE_STATUS_ISSUED,
    LICENSE_STATUS_REVOKED,
    LICENSE_STATUS_SUSPENDED,
)
from app.licensing.downloads import (
    find_entitling_license,
    hash_download_token,
    installer_customer_eligible,
    license_entitles_download,
    mint_download_token,
    redeem_download_token,
    serialize_installer_customer,
    set_installer_channel,
    set_installer_listing,
)
from app.licensing.installer_storage import (
    build_installer_storage_key,
    clear_memory_store,
    put_installer_bytes,
    sanitize_installer_filename,
)
from app.licensing.models import DesktopDownloadToken, DesktopInstaller, DesktopLicense, DesktopProduct


def _settings(**kwargs) -> Settings:
    base = dict(
        enable_desktop_licensing=True,
        installer_storage_backend="memory",
        installer_download_token_ttl_seconds=120,
        installer_presign_get_ttl_seconds=60,
        installer_max_upload_bytes=1024 * 1024,
    )
    base.update(kwargs)
    return Settings(**base)


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


def _installer(**kwargs) -> DesktopInstaller:
    defaults = dict(
        product_id=1,
        version="1.0.0",
        release_channel=INSTALLER_CHANNEL_CURRENT,
        listing_active=1,
        storage_key="desktop-installers/QR_CODE/1.0.0/app.exe",
        file_name="app.exe",
        file_sha256="a" * 64,
        file_size_bytes=100,
    )
    defaults.update(kwargs)
    row = DesktopInstaller(**defaults)
    row.id = kwargs.get("id", 50)
    return row


def test_sanitize_rejects_path_traversal_and_bad_types():
    with pytest.raises(ValueError):
        sanitize_installer_filename("../evil.exe")
    with pytest.raises(ValueError):
        sanitize_installer_filename("/abs/path.exe")
    with pytest.raises(ValueError):
        sanitize_installer_filename("C:\\Windows\\x.exe")
    with pytest.raises(ValueError):
        sanitize_installer_filename("notes.txt")
    assert "EXE" in sanitize_installer_filename("My App (1).EXE") or "exe" in sanitize_installer_filename(
        "My App (1).EXE"
    ).lower()


def test_sanitize_ok_exe():
    assert sanitize_installer_filename("Setup.msi").endswith(".msi")
    assert sanitize_installer_filename("app.zip") == "app.zip"


def test_storage_key_server_generated():
    key = build_installer_storage_key(product_code="QR_CODE", version="1.2.3", safe_filename="app.exe")
    assert key == "desktop-installers/QR_CODE/1.2.3/app.exe"
    with pytest.raises(ValueError):
        build_installer_storage_key(product_code="../x", version="1", safe_filename="a.exe")


def test_put_bytes_sha256_authoritative():
    clear_memory_store()
    settings = _settings()
    data = b"installer-bytes-xyz"
    put = put_installer_bytes(
        settings,
        storage_key="desktop-installers/QR_CODE/1.0.0/app.exe",
        data=data,
        content_type="application/octet-stream",
    )
    import hashlib

    assert put.file_sha256 == hashlib.sha256(data).hexdigest()
    assert put.file_size_bytes == len(data)


def test_oversized_upload_rejected():
    settings = _settings(installer_max_upload_bytes=10)
    with pytest.raises(ValueError):
        put_installer_bytes(
            settings,
            storage_key="desktop-installers/QR_CODE/1.0.0/app.exe",
            data=b"0123456789abcdef",
        )


def test_license_entitlement_rules():
    now = datetime.now(timezone.utc)
    assert license_entitles_download(_license(status=LICENSE_STATUS_ISSUED, expires_at=now + timedelta(days=1)))
    assert license_entitles_download(_license(status=LICENSE_STATUS_ACTIVE, expires_at=None))
    assert not license_entitles_download(_license(status=LICENSE_STATUS_REVOKED))
    assert not license_entitles_download(_license(status=LICENSE_STATUS_SUSPENDED))
    assert not license_entitles_download(_license(status=LICENSE_STATUS_EXPIRED))
    # Phase 7A: valid trials may download
    assert license_entitles_download(
        _license(
            entitlement_type=ENTITLEMENT_TRIAL,
            status=LICENSE_STATUS_ISSUED,
            expires_at=now + timedelta(days=7),
        )
    )
    assert not license_entitles_download(
        _license(
            entitlement_type=ENTITLEMENT_TRIAL,
            status=LICENSE_STATUS_ISSUED,
            expires_at=now - timedelta(seconds=1),
        )
    )
    # Wall-clock expiry even if status still issued
    assert not license_entitles_download(
        _license(status=LICENSE_STATUS_ISSUED, expires_at=now - timedelta(seconds=1))
    )


def test_installer_customer_eligible():
    assert installer_customer_eligible(_installer())
    assert not installer_customer_eligible(_installer(listing_active=0))
    assert not installer_customer_eligible(_installer(release_channel=INSTALLER_CHANNEL_ARCHIVED))
    assert not installer_customer_eligible(_installer(storage_key=None))
    assert not installer_customer_eligible(_installer(file_sha256=None))


def test_customer_serialize_excludes_storage_secrets():
    product = DesktopProduct(code="QR_CODE", name="QR")
    product.id = 1
    out = serialize_installer_customer(_installer(), product=product)
    assert "storage_key" not in out
    assert "storage_url" not in out
    assert "aws" not in str(out).lower()
    assert out["file_sha256"]


def test_find_entitling_cross_user():
    user = SimpleNamespace(id=7)
    foreign = _license(licensed_user_id=99)
    db = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [foreign]
    db.execute.return_value = result
    assert find_entitling_license(db, user=user, product_id=1) is None


def test_mint_requires_entitlement():
    settings = _settings()
    user = SimpleNamespace(id=7)
    inst = _installer()
    db = MagicMock()
    db.get.return_value = inst

    def execute(stmt):
        result = MagicMock()
        result.scalars.return_value.all.return_value = []  # no licenses
        return result

    db.execute.side_effect = execute
    with pytest.raises(HTTPException) as exc:
        mint_download_token(db, settings, user=user, installer_id=50)
    assert exc.value.status_code == 403


def test_mint_and_redeem_happy_path_and_single_use():
    clear_memory_store()
    settings = _settings()
    put_installer_bytes(
        settings,
        storage_key="desktop-installers/QR_CODE/1.0.0/app.exe",
        data=b"abc",
    )
    user = SimpleNamespace(id=7)
    inst = _installer()
    lic = _license()
    raw = "opaque-token-value"
    tok_row = DesktopDownloadToken(
        token_hash=hash_download_token(raw),
        user_id=7,
        installer_id=50,
        license_id=101,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=2),
    )
    tok_row.id = 9

    db = MagicMock()

    def get(model, ident):
        if model is DesktopInstaller:
            return inst
        if model is DesktopLicense:
            return lic
        return None

    db.get.side_effect = get

    def execute(stmt):
        result = MagicMock()
        result.scalar_one_or_none.return_value = tok_row
        result.scalars.return_value.all.return_value = [lic]
        result.rowcount = 1
        return result

    db.execute.side_effect = execute

    with patch("app.licensing.downloads.record_license_event"):
        out = redeem_download_token(db, settings, user=user, raw_token=raw)
        assert "download_url" in out
        assert "AWS_SECRET" not in out["download_url"]
        assert out["file_sha256"]

        tok_row.used_at = datetime.now(timezone.utc)

        def execute2(stmt):
            result = MagicMock()
            result.scalar_one_or_none.return_value = tok_row
            result.rowcount = 0
            return result

        db.execute.side_effect = execute2
        with pytest.raises(HTTPException) as exc:
            redeem_download_token(db, settings, user=user, raw_token=raw)
        assert exc.value.status_code == 409


def test_redeem_wrong_user_denied():
    settings = _settings()
    tok_row = DesktopDownloadToken(
        token_hash=hash_download_token("tok"),
        user_id=7,
        installer_id=50,
        license_id=101,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=2),
    )
    tok_row.id = 1
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = tok_row
    db.execute.return_value = result
    with pytest.raises(HTTPException) as exc:
        redeem_download_token(db, settings, user=SimpleNamespace(id=99), raw_token="tok")
    assert exc.value.status_code == 404


def test_redeem_expired_token():
    settings = _settings()
    tok_row = DesktopDownloadToken(
        token_hash=hash_download_token("tok"),
        user_id=7,
        installer_id=50,
        license_id=101,
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=5),
    )
    tok_row.id = 1
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = tok_row
    db.execute.return_value = result
    with pytest.raises(HTTPException) as exc:
        redeem_download_token(db, settings, user=SimpleNamespace(id=7), raw_token="tok")
    assert exc.value.status_code == 410


def test_redeem_rechecks_expired_license():
    settings = _settings()
    inst = _installer()
    lic = _license(expires_at=datetime.now(timezone.utc) - timedelta(days=1), status=LICENSE_STATUS_ISSUED)
    tok_row = DesktopDownloadToken(
        token_hash=hash_download_token("tok"),
        user_id=7,
        installer_id=50,
        license_id=101,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=2),
    )
    tok_row.id = 1
    db = MagicMock()

    def get(model, ident):
        if model is DesktopInstaller:
            return inst
        if model is DesktopLicense:
            return lic
        return None

    db.get.side_effect = get

    def execute(stmt):
        result = MagicMock()
        result.scalar_one_or_none.return_value = tok_row
        result.scalars.return_value.all.return_value = [lic]
        result.rowcount = 1
        return result

    db.execute.side_effect = execute
    with pytest.raises(HTTPException) as exc:
        redeem_download_token(db, settings, user=SimpleNamespace(id=7), raw_token="tok")
    assert exc.value.status_code == 403


def test_publish_requires_file():
    db = MagicMock()
    row = _installer(storage_key=None, file_sha256=None)
    db.get.return_value = row
    with pytest.raises(HTTPException) as exc:
        set_installer_listing(db, admin=SimpleNamespace(id=1), installer_id=50, listing_active=True)
    assert exc.value.status_code == 400


def test_set_current_demotes_peer():
    db = MagicMock()
    row = _installer(id=50, release_channel=INSTALLER_CHANNEL_RECOMMENDED)
    peer = _installer(id=51, release_channel=INSTALLER_CHANNEL_CURRENT)
    db.get.return_value = row
    result = MagicMock()
    result.scalars.return_value.all.return_value = [peer]
    db.execute.return_value = result
    with patch("app.licensing.downloads.record_license_event"):
        out = set_installer_channel(db, admin=SimpleNamespace(id=1), installer_id=50, channel="current")
    assert out.release_channel == INSTALLER_CHANNEL_CURRENT
    assert peer.release_channel == INSTALLER_CHANNEL_RECOMMENDED


def test_archive_unpublishes():
    db = MagicMock()
    row = _installer(listing_active=1)
    db.get.return_value = row
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    db.execute.return_value = result
    with patch("app.licensing.downloads.record_license_event"):
        out = set_installer_channel(db, admin=SimpleNamespace(id=1), installer_id=50, channel="archived")
    assert out.release_channel == INSTALLER_CHANNEL_ARCHIVED
    assert out.listing_active == 0


def test_feature_flag_off_blocks_download_routes(monkeypatch):
    from fastapi.testclient import TestClient

    import app.licensing.feature_flag as ff
    from app.main import create_app

    monkeypatch.setattr(ff, "get_settings", lambda: Settings(enable_desktop_licensing=False))
    app = create_app()
    app.state.startup_complete = True
    app.state.startup_status = "ok"
    client = TestClient(app)
    assert client.get("/api/desktop/downloads").status_code == 404
    assert client.post("/api/desktop/downloads/installers/1/token").status_code == 404
    assert client.get("/api/admin/desktop/products/1/installers").status_code == 404


def test_unauthenticated_admin_installers_denied(monkeypatch):
    from fastapi.testclient import TestClient

    import app.licensing.feature_flag as ff
    from app.main import create_app

    monkeypatch.setattr(ff, "get_settings", lambda: Settings(enable_desktop_licensing=True))
    app = create_app()
    app.state.startup_complete = True
    app.state.startup_status = "ok"
    client = TestClient(app)
    assert client.get("/api/admin/desktop/products/1/installers").status_code == 401
    assert client.post("/api/admin/desktop/installers/1/publish").status_code == 401


def test_token_hash_only_not_plaintext_persisted():
    raw = "super-secret-token"
    h = hash_download_token(raw)
    assert h != raw
    assert len(h) == 64
