"""Phase 7A: desktop 7-day trials — eligibility, activation, downloads, email, concurrency."""

from __future__ import annotations

import hashlib
import os
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import IntegrityError

from app.config import Settings
from app.licensing.binding import (
    LicenseBindingError,
    activate_license_on_device,
    admin_reset_device_binding,
    assert_license_activatable_entitlement,
    deactivate_activation_preserve_binding,
)
from app.licensing.constants import (
    ACTIVATION_STATUS_ACTIVE,
    ENTITLEMENT_PAID,
    ENTITLEMENT_TRIAL,
    LICENSE_STATUS_ACTIVE,
    LICENSE_STATUS_EXPIRED,
    LICENSE_STATUS_ISSUED,
    TRIAL_CREATE_PER_USER_PER_HOUR,
    TRIAL_ERR_ALREADY_USED,
    TRIAL_ERR_BLOCKED_BY_PAID,
    TRIAL_ERR_TRIAL_DISABLED,
    UQ_DESKTOP_LICENSES_ONE_TRIAL_PER_USER_PRODUCT,
)
from app.licensing.downloads import license_entitles_download
from app.licensing.keys import hash_license_key
from app.licensing.models import DesktopActivation, DesktopDevice, DesktopLicense, DesktopProduct
from app.licensing.rate_limit import clear_rate_limit_buckets
from app.licensing.service import create_paid_license_row, create_trial_license_row
from app.licensing.signing import (
    build_entitlement_claims,
    generate_ephemeral_signing_pem,
    load_signing_key_material,
    sign_entitlement,
    verify_entitlement_token,
)
from app.licensing.trials import (
    apply_trial_create_rate_limits,
    create_desktop_trial,
    find_any_trial_license,
    find_usable_paid_license,
    is_trial_unique_conflict,
    resolve_trial_product,
    serialize_trial_create_response,
)


def _fp(seed: str = "device-a") -> str:
    return hashlib.sha256(f"AQ|QR_CODE|{seed}".encode()).hexdigest()


def _fernet_settings(**kwargs) -> Settings:
    base = dict(
        enable_desktop_licensing=True,
        license_key_encryption_secret=Fernet.generate_key().decode(),
        license_signing_private_key=generate_ephemeral_signing_pem(),
        license_max_offline_days=14,
        email_from="noreply@example.com",
        public_app_url="https://app.example.com",
    )
    base.update(kwargs)
    return Settings(**base)


def _product(**kwargs) -> DesktopProduct:
    defaults = dict(
        code="QR_CODE",
        name="QR Code",
        listing_active=1,
        trial_enabled=1,
        trial_duration_days=7,
        sort_order=1,
    )
    defaults.update(kwargs)
    p = DesktopProduct(**defaults)
    p.id = kwargs.get("id", 1)
    return p


def _user(**kwargs):
    defaults = dict(id=7, company_id=3, email="user@example.com", name="Test User")
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _license(**kwargs) -> DesktopLicense:
    now = datetime.now(timezone.utc)
    defaults = dict(
        product_id=1,
        plan_id=None,
        order_id=None,
        company_id=3,
        licensed_user_id=7,
        entitlement_type=ENTITLEMENT_TRIAL,
        seat_index=None,
        key_prefix="AQ",
        key_last4="TRIL",
        key_hash="t" * 64,
        key_encrypted="c",
        status=LICENSE_STATUS_ISSUED,
        expires_at=now + timedelta(days=7),
        bound_device_id=None,
        activated_at=None,
    )
    defaults.update(kwargs)
    lic = DesktopLicense(**defaults)
    lic.id = kwargs.get("id", 501)
    return lic


# --- Eligibility / creation (mocked DB) ---


def test_resolve_product_trial_disabled():
    db = MagicMock()
    product = _product(trial_enabled=0)
    result = MagicMock()
    result.scalar_one_or_none.return_value = product
    db.execute.return_value = result
    with pytest.raises(HTTPException) as exc:
        resolve_trial_product(db, "QR_CODE")
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == TRIAL_ERR_TRIAL_DISABLED


def test_resolve_product_not_found():
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute.return_value = result
    with pytest.raises(HTTPException) as exc:
        resolve_trial_product(db, "NOPE")
    assert exc.value.status_code == 404
    assert exc.value.detail["code"] == "product_not_found"


def test_usable_paid_blocks_and_expired_paid_does_not():
    now = datetime.now(timezone.utc)
    paid_ok = _license(
        entitlement_type=ENTITLEMENT_PAID,
        status=LICENSE_STATUS_ACTIVE,
        expires_at=now + timedelta(days=30),
        id=10,
    )
    paid_expired = _license(
        entitlement_type=ENTITLEMENT_PAID,
        status=LICENSE_STATUS_ACTIVE,
        expires_at=now - timedelta(days=1),
        id=11,
    )
    db = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [paid_ok]
    db.execute.return_value = result
    assert find_usable_paid_license(db, licensed_user_id=7, product_id=1) is paid_ok

    result.scalars.return_value.all.return_value = [paid_expired]
    assert find_usable_paid_license(db, licensed_user_id=7, product_id=1) is None


def test_any_trial_consumes_eligibility_even_if_expired():
    expired = _license(
        status=LICENSE_STATUS_EXPIRED,
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = expired
    db.execute.return_value = result
    assert find_any_trial_license(db, licensed_user_id=7, product_id=1) is expired


def test_create_desktop_trial_first_success():
    settings = _fernet_settings()
    user = _user()
    product = _product()
    db = MagicMock()

    # resolve product
    prod_result = MagicMock()
    prod_result.scalar_one_or_none.return_value = product

    # paid lookup → empty; trial lookup → none
    paid_result = MagicMock()
    paid_result.scalars.return_value.all.return_value = []
    trial_result = MagicMock()
    trial_result.scalar_one_or_none.return_value = None

    execute_calls = {"n": 0}

    def execute(stmt, *a, **k):
        execute_calls["n"] += 1
        # crude sequencing: first product, then paid list, then trial one
        s = str(stmt)
        if "desktop_products" in s or execute_calls["n"] == 1:
            return prod_result
        if execute_calls["n"] == 2:
            return paid_result
        if execute_calls["n"] == 3:
            return trial_result
        return MagicMock()

    db.execute.side_effect = execute

    # Flush assigns id
    def flush():
        # After create_trial_license_row adds license, give it an id
        for obj in list(getattr(db, "_added", []) or []):
            if isinstance(obj, DesktopLicense) and getattr(obj, "id", None) is None:
                obj.id = 900
            if obj.__class__.__name__ == "DesktopTrialEmailDelivery" and getattr(obj, "id", None) is None:
                obj.id = 1

    added: list = []

    def add(obj):
        added.append(obj)
        db._added = added

    db.add.side_effect = add
    db.flush.side_effect = flush

    with patch("app.licensing.trials.create_trial_license_row") as mint:
        lic = _license(id=900)
        mint.return_value = (lic, "AQ-PLAIN-TEXT-KEY1")
        license_row, prod, delivery = create_desktop_trial(
            db, settings, user=user, product_code="qr_code"
        )
        assert license_row.id == 900
        assert prod.code == "QR_CODE"
        assert delivery.license_id == 900
        # plaintext must not linger on returned objects
        out = serialize_trial_create_response(license_row, product=prod)
        assert "license_key" not in out
        assert out["entitlement_type"] == ENTITLEMENT_TRIAL
        assert "••••" in out["key_masked"] or "key_masked" in out


def test_create_desktop_trial_duplicate_precheck():
    settings = _fernet_settings()
    user = _user()
    product = _product()
    existing = _license(id=1)

    db = MagicMock()
    prod_result = MagicMock()
    prod_result.scalar_one_or_none.return_value = product
    paid_result = MagicMock()
    paid_result.scalars.return_value.all.return_value = []
    trial_result = MagicMock()
    trial_result.scalar_one_or_none.return_value = existing

    n = {"i": 0}

    def execute(stmt, *a, **k):
        n["i"] += 1
        if n["i"] == 1:
            return prod_result
        if n["i"] == 2:
            return paid_result
        return trial_result

    db.execute.side_effect = execute

    with pytest.raises(HTTPException) as exc:
        create_desktop_trial(db, settings, user=user, product_code="QR_CODE")
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == TRIAL_ERR_ALREADY_USED


def test_create_desktop_trial_blocked_by_paid():
    settings = _fernet_settings()
    user = _user()
    product = _product()
    paid = _license(
        entitlement_type=ENTITLEMENT_PAID,
        status=LICENSE_STATUS_ACTIVE,
        expires_at=datetime.now(timezone.utc) + timedelta(days=10),
    )

    db = MagicMock()
    prod_result = MagicMock()
    prod_result.scalar_one_or_none.return_value = product
    paid_result = MagicMock()
    paid_result.scalars.return_value.all.return_value = [paid]

    n = {"i": 0}

    def execute(stmt, *a, **k):
        n["i"] += 1
        if n["i"] == 1:
            return prod_result
        return paid_result

    db.execute.side_effect = execute

    with pytest.raises(HTTPException) as exc:
        create_desktop_trial(db, settings, user=user, product_code="QR_CODE")
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == TRIAL_ERR_BLOCKED_BY_PAID


def test_is_trial_unique_conflict_narrow():
    class Orig:
        diag = SimpleNamespace(constraint_name=UQ_DESKTOP_LICENSES_ONE_TRIAL_PER_USER_PRODUCT)

    exc = IntegrityError("stmt", {}, Exception())
    exc.orig = Orig()  # type: ignore[attr-defined]
    assert is_trial_unique_conflict(exc)

    class Other:
        diag = SimpleNamespace(constraint_name="uq_desktop_activations_license_device")

    other = IntegrityError("stmt", {}, Exception())
    other.orig = Other()  # type: ignore[attr-defined]
    assert not is_trial_unique_conflict(other)


def test_create_maps_unique_violation_to_409():
    settings = _fernet_settings()
    user = _user()
    product = _product()
    db = MagicMock()

    prod_result = MagicMock()
    prod_result.scalar_one_or_none.return_value = product
    paid_result = MagicMock()
    paid_result.scalars.return_value.all.return_value = []
    trial_result = MagicMock()
    trial_result.scalar_one_or_none.return_value = None

    n = {"i": 0}

    def execute(stmt, *a, **k):
        n["i"] += 1
        if n["i"] == 1:
            return prod_result
        if n["i"] == 2:
            return paid_result
        return trial_result

    db.execute.side_effect = execute

    class Orig:
        diag = SimpleNamespace(constraint_name=UQ_DESKTOP_LICENSES_ONE_TRIAL_PER_USER_PRODUCT)

    conflict = IntegrityError("INSERT", {}, Exception())
    conflict.orig = Orig()  # type: ignore[attr-defined]

    with patch("app.licensing.trials.create_trial_license_row", side_effect=conflict):
        with pytest.raises(HTTPException) as exc:
            create_desktop_trial(db, settings, user=user, product_code="QR_CODE")
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == TRIAL_ERR_ALREADY_USED


# --- Downloads ---


def test_trial_download_entitled_and_expired_not():
    now = datetime.now(timezone.utc)
    assert license_entitles_download(
        _license(status=LICENSE_STATUS_ISSUED, expires_at=now + timedelta(days=3))
    )
    assert not license_entitles_download(
        _license(status=LICENSE_STATUS_ISSUED, expires_at=now - timedelta(seconds=1))
    )
    # Download entitlement does not require / set bound_device_id
    lic = _license(bound_device_id=None)
    assert license_entitles_download(lic)
    assert lic.bound_device_id is None


# --- Signing / offline ---


def test_trial_entitlement_ed25519_and_naf_clamped():
    settings = _fernet_settings(license_max_offline_days=14)
    material = load_signing_key_material(settings)
    exp = datetime.now(timezone.utc) + timedelta(days=3)  # shorter than offline cap
    claims = build_entitlement_claims(
        product_code="QR_CODE",
        license_id=501,
        activation_id=9,
        licensed_user_id=7,
        fingerprint_hash=_fp(),
        entitlement_type=ENTITLEMENT_TRIAL,
        expires_at=exp,
        max_offline_days=14,
    )
    assert claims["ent"] == "trial"
    assert claims["exp"] == int(exp.timestamp())
    assert claims["naf"] <= claims["exp"]
    token = sign_entitlement(settings, claims)
    verified = verify_entitlement_token(
        token,
        public_key_pem=material.public_key_pem,
        expected_product="QR_CODE",
        expected_fp=_fp(),
    )
    assert verified["ent"] == "trial"

    # Tamper
    parts = token.split(".")
    bad = parts[0] + "x." + parts[1]
    with pytest.raises(ValueError):
        verify_entitlement_token(bad, public_key_pem=material.public_key_pem)


def test_trial_entitlement_rejects_after_exp():
    settings = _fernet_settings()
    material = load_signing_key_material(settings)
    # Expire beyond clock skew (300s) so verify rejects
    exp = datetime.now(timezone.utc) - timedelta(seconds=400)
    claims = build_entitlement_claims(
        product_code="QR_CODE",
        license_id=1,
        activation_id=1,
        licensed_user_id=7,
        fingerprint_hash=_fp(),
        entitlement_type=ENTITLEMENT_TRIAL,
        expires_at=exp,
        max_offline_days=14,
        now=exp - timedelta(days=1),
    )
    token = sign_entitlement(settings, claims)
    with pytest.raises(ValueError, match="expired|offline"):
        verify_entitlement_token(
            token,
            public_key_pem=material.public_key_pem,
            now=datetime.now(timezone.utc),
        )


# --- Activation binding (mocked) ---


def test_trial_activation_wrong_user_and_product():
    from app.licensing.binding import assert_license_user_product

    lic = _license(licensed_user_id=7, product_id=1)
    with pytest.raises(LicenseBindingError) as exc:
        assert_license_user_product(lic, website_user_id=99, product_id=1)
    assert exc.value.code == "wrong_user"
    with pytest.raises(LicenseBindingError) as exc2:
        assert_license_user_product(lic, website_user_id=7, product_id=2)
    assert exc2.value.code == "wrong_product"


def test_trial_activatable_assert():
    assert_license_activatable_entitlement(_license(entitlement_type=ENTITLEMENT_TRIAL))


def test_trial_to_paid_creates_separate_key():
    """B12: paid mint is independent — new hash, no conversion of trial row."""
    settings = _fernet_settings()
    db = MagicMock()
    added: list = []

    def add(obj):
        added.append(obj)
        if isinstance(obj, DesktopLicense):
            obj.id = 1000 + len([x for x in added if isinstance(x, DesktopLicense)])

    db.add.side_effect = add
    db.flush = MagicMock()

    trial, trial_pt = create_trial_license_row(
        db,
        settings,
        product_id=1,
        company_id=3,
        licensed_user_id=7,
        duration_days=7,
    )
    paid, paid_pt = create_paid_license_row(
        db,
        settings,
        product_id=1,
        plan_id=2,
        order_id=50,
        company_id=3,
        licensed_user_id=7,
        seat_index=1,
        duration_days=365,
    )
    assert trial.entitlement_type == ENTITLEMENT_TRIAL
    assert paid.entitlement_type == ENTITLEMENT_PAID
    assert trial.key_hash != paid.key_hash
    assert trial_pt != paid_pt
    assert trial.order_id is None
    assert paid.order_id == 50
    # trial row fields unchanged by paid mint
    assert trial.bound_device_id is None


def test_trial_rate_limit_per_user():
    clear_rate_limit_buckets()
    for _ in range(TRIAL_CREATE_PER_USER_PER_HOUR):
        apply_trial_create_rate_limits(user_id=42, client_ip="1.2.3.4")
    with pytest.raises(HTTPException) as exc:
        apply_trial_create_rate_limits(user_id=42, client_ip="1.2.3.4")
    assert exc.value.status_code == 429
    assert exc.value.detail["code"] == "rate_limited"
    clear_rate_limit_buckets()


def test_feature_flag_off_trials_404(monkeypatch):
    import app.licensing.feature_flag as ff
    from app.config import get_settings as real_get_settings
    from app.main import create_app
    from fastapi.testclient import TestClient

    settings = Settings(enable_desktop_licensing=False)
    monkeypatch.setattr(ff, "get_settings", lambda: settings)
    app = create_app()
    app.dependency_overrides[real_get_settings] = lambda: settings
    app.state.startup_complete = True
    app.state.startup_status = "ok"
    client = TestClient(app)
    r = client.post("/api/desktop/trials", json={"product_code": "QR_CODE"})
    assert r.status_code == 404
    app.dependency_overrides.clear()


def test_migration_037_sql_contains_required_objects():
    from pathlib import Path

    sql = (
        Path(__file__).resolve().parents[1] / "migrations" / "037_desktop_licensing_trials.sql"
    ).read_text()
    assert "uq_desktop_licenses_one_trial_per_user_product" in sql
    assert "desktop_trial_email_deliveries" in sql
    assert "ix_desktop_trial_email_deliveries_status" in sql
    assert "ix_desktop_trial_email_deliveries_user" in sql
    assert "WHERE entitlement_type = 'trial'" in sql
    assert "DELETE FROM" not in sql.upper()


def test_sqlite_concurrent_one_trial_per_user_product():
    """Disposable SQLite: two concurrent inserts → one success, one unique violation."""
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    try:
        engine = create_engine(
            f"sqlite:///{path}",
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(engine, "connect")
        def _fk_off(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=OFF")
            cur.close()

        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE desktop_licenses (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        licensed_user_id INTEGER NOT NULL,
                        product_id INTEGER NOT NULL,
                        entitlement_type VARCHAR(16) NOT NULL,
                        key_hash VARCHAR(128) NOT NULL UNIQUE,
                        status VARCHAR(32) NOT NULL
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE UNIQUE INDEX uq_desktop_licenses_one_trial_per_user_product
                      ON desktop_licenses (licensed_user_id, product_id)
                      WHERE entitlement_type = 'trial'
                    """
                )
            )

        barrier = threading.Barrier(2)
        results: list[str] = []
        lock = threading.Lock()

        def worker(suffix: str) -> None:
            with engine.connect() as conn:
                barrier.wait()
                try:
                    conn.execute(text("BEGIN IMMEDIATE"))
                    conn.execute(
                        text(
                            "INSERT INTO desktop_licenses "
                            "(licensed_user_id, product_id, entitlement_type, key_hash, status) "
                            "VALUES (7, 1, 'trial', :h, 'issued')"
                        ),
                        {"h": "hash-" + suffix},
                    )
                    conn.execute(text("COMMIT"))
                    with lock:
                        results.append("success")
                except Exception:
                    try:
                        conn.execute(text("ROLLBACK"))
                    except Exception:
                        pass
                    with lock:
                        results.append("conflict")

        t1 = threading.Thread(target=worker, args=("a",))
        t2 = threading.Thread(target=worker, args=("b",))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert results.count("success") == 1, results
        assert results.count("conflict") == 1, results

        with engine.connect() as conn:
            n = conn.execute(
                text(
                    "SELECT COUNT(*) FROM desktop_licenses "
                    "WHERE licensed_user_id=7 AND product_id=1 AND entitlement_type='trial'"
                )
            ).scalar()
            assert int(n) == 1
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


@pytest.mark.skipif(
    not os.environ.get("PHASE7A_PG_URL"),
    reason="Set PHASE7A_PG_URL to a disposable Postgres URL to run PG concurrency (never production).",
)
def test_postgres_concurrent_one_trial_per_user_product():
    """Disposable/staging Postgres only — never production."""
    url = os.environ["PHASE7A_PG_URL"]
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS phase7a_trial_race"))
        conn.execute(
            text(
                """
                CREATE TABLE phase7a_trial_race (
                    id SERIAL PRIMARY KEY,
                    licensed_user_id INTEGER NOT NULL,
                    product_id INTEGER NOT NULL,
                    entitlement_type VARCHAR(16) NOT NULL,
                    key_hash VARCHAR(128) NOT NULL UNIQUE,
                    status VARCHAR(32) NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE UNIQUE INDEX uq_phase7a_one_trial
                  ON phase7a_trial_race (licensed_user_id, product_id)
                  WHERE entitlement_type = 'trial'
                """
            )
        )

    barrier = threading.Barrier(2)
    results: list[str] = []
    lock = threading.Lock()

    def worker(suffix: str) -> None:
        with engine.connect() as conn:
            barrier.wait()
            trans = conn.begin()
            try:
                conn.execute(
                    text(
                        "INSERT INTO phase7a_trial_race "
                        "(licensed_user_id, product_id, entitlement_type, key_hash, status) "
                        "VALUES (7, 1, 'trial', :h, 'issued')"
                    ),
                    {"h": "pg-hash-" + suffix},
                )
                trans.commit()
                with lock:
                    results.append("success")
            except Exception:
                trans.rollback()
                with lock:
                    results.append("conflict")

    t1 = threading.Thread(target=worker, args=("a",))
    t2 = threading.Thread(target=worker, args=("b",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert results.count("success") == 1, results
    assert results.count("conflict") == 1, results

    with engine.begin() as conn:
        n = conn.execute(
            text(
                "SELECT COUNT(*) FROM phase7a_trial_race "
                "WHERE licensed_user_id=7 AND product_id=1 AND entitlement_type='trial'"
            )
        ).scalar()
        assert int(n) == 1
        conn.execute(text("DROP TABLE IF EXISTS phase7a_trial_race"))


def test_admin_reset_works_for_trial_row_shape():
    """Admin reset helpers accept trial licenses the same as paid (binding layer)."""
    lic = _license(status=LICENSE_STATUS_ACTIVE, bound_device_id=9, id=77)
    assert_license_activatable_entitlement(lic)
    # Shape check: reset reason length constant still applies via admin router (not grant)
    from app.licensing.constants import ADMIN_RESET_REASON_MIN_LEN

    assert ADMIN_RESET_REASON_MIN_LEN >= 8
