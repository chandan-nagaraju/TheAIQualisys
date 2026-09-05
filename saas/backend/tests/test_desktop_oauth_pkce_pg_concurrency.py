"""Optional PostgreSQL concurrency tests for desktop OAuth (Phase 9C-D).

Skipped unless OAUTH_PG_URL points at a disposable Postgres database.
Never point this at production.
"""

from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.oauth import service as oauth_service
from app.oauth.constants import GRANT_AUTHORIZATION_CODE, GRANT_REFRESH_TOKEN, SCOPE_DESKTOP_LICENSE
from app.oauth.errors import OAuthError
from app.oauth.pkce import challenge_s256, generate_code_verifier, hash_secret

OAUTH_PG_URL = os.environ.get("OAUTH_PG_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not OAUTH_PG_URL,
    reason="Set OAUTH_PG_URL to a disposable Postgres URL to run OAuth concurrency tests (never production).",
)


def _engine():
    return create_engine(OAUTH_PG_URL, pool_size=6, max_overflow=4)


def _bootstrap(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS oauth_desktop_audit_events CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS oauth_refresh_sessions CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS oauth_authorization_codes CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS oauth_desktop_clients CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS company_users CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS companies CASCADE"))
        conn.execute(
            text(
                """
                CREATE TABLE companies (
                    id SERIAL PRIMARY KEY,
                    company_name VARCHAR(255) NOT NULL DEFAULT 'Test Co'
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE company_users (
                    id SERIAL PRIMARY KEY,
                    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                    email VARCHAR(255) NOT NULL,
                    password_hash VARCHAR(255) NOT NULL DEFAULT 'x',
                    name VARCHAR(255) NOT NULL DEFAULT 'User',
                    is_blocked INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )

    migration = Path(__file__).resolve().parents[1] / "migrations" / "038_desktop_oauth_pkce.sql"
    with engine.begin() as conn:
        conn.execute(text(migration.read_text()))


def _seed(engine) -> tuple[str, int, int, str, str, str]:
    verifier = generate_code_verifier()
    challenge = challenge_s256(verifier)
    client_id = "qr-code-desktop-staging"
    redirect = "aiqualisys-qr://oauth/callback"
    with engine.begin() as conn:
        company_id = conn.execute(
            text("INSERT INTO companies (company_name) VALUES ('OAuth Race Co') RETURNING id")
        ).scalar_one()
        user_id = conn.execute(
            text(
                "INSERT INTO company_users (company_id, email, name, is_blocked) "
                "VALUES (:c, 'oauth-race@example.test', 'Race', 0) RETURNING id"
            ),
            {"c": company_id},
        ).scalar_one()
        conn.execute(
            text(
                """
                INSERT INTO oauth_desktop_clients
                  (client_id, client_name, client_type, redirect_uris, allowed_scopes, enabled)
                VALUES
                  (:cid, 'QR Desktop', 'public', CAST(:ru AS jsonb), CAST(:sc AS jsonb), 1)
                """
            ),
            {
                "cid": client_id,
                "ru": f'["{redirect}"]',
                "sc": f'["{SCOPE_DESKTOP_LICENSE}"]',
            },
        )
    return client_id, int(user_id), int(company_id), verifier, challenge, redirect


def test_postgres_concurrent_authorization_code_exchange_single_winner():
    engine = _engine()
    _bootstrap(engine)
    client_id, user_id, company_id, verifier, challenge, redirect = _seed(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    db = SessionLocal()
    try:
        user = SimpleNamespace(id=user_id, company_id=company_id, is_blocked=0)
        client = oauth_service.get_enabled_client(db, client_id)
        code = oauth_service.issue_authorization_code(
            db,
            user=user,
            client=client,
            redirect_uri=redirect,
            scope=SCOPE_DESKTOP_LICENSE,
            state="race-state",
            code_challenge=challenge,
        )
        db.commit()
    finally:
        db.close()

    barrier = threading.Barrier(2)
    results: list[str] = []
    lock = threading.Lock()

    def worker() -> None:
        s = SessionLocal()
        try:
            barrier.wait(timeout=10)
            oauth_service.exchange_authorization_code(
                s,
                grant_type=GRANT_AUTHORIZATION_CODE,
                code=code,
                client_id=client_id,
                redirect_uri=redirect,
                code_verifier=verifier,
            )
            with lock:
                results.append("ok")
        except OAuthError:
            s.rollback()
            with lock:
                results.append("fail")
        except Exception:
            s.rollback()
            with lock:
                results.append("error")
            raise
        finally:
            s.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futs = [pool.submit(worker), pool.submit(worker)]
        for f in futs:
            f.result(timeout=30)

    assert results.count("ok") == 1, results
    assert results.count("fail") == 1, results

    with engine.connect() as conn:
        used = conn.execute(
            text("SELECT used_at IS NOT NULL FROM oauth_authorization_codes WHERE code_hash=:h"),
            {"h": hash_secret(code)},
        ).scalar_one()
        assert used is True


def test_postgres_concurrent_refresh_replay_revokes_family():
    engine = _engine()
    _bootstrap(engine)
    client_id, user_id, company_id, verifier, challenge, redirect = _seed(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    db = SessionLocal()
    try:
        user = SimpleNamespace(id=user_id, company_id=company_id, is_blocked=0)
        client = oauth_service.get_enabled_client(db, client_id)
        code = oauth_service.issue_authorization_code(
            db,
            user=user,
            client=client,
            redirect_uri=redirect,
            scope=SCOPE_DESKTOP_LICENSE,
            state="refresh-race",
            code_challenge=challenge,
        )
        db.commit()
        tokens = oauth_service.exchange_authorization_code(
            db,
            grant_type=GRANT_AUTHORIZATION_CODE,
            code=code,
            client_id=client_id,
            redirect_uri=redirect,
            code_verifier=verifier,
        )
        refresh = tokens["refresh_token"]
    finally:
        db.close()

    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    lock = threading.Lock()

    def worker() -> None:
        s = SessionLocal()
        try:
            barrier.wait(timeout=10)
            oauth_service.refresh_access_token(
                s,
                grant_type=GRANT_REFRESH_TOKEN,
                refresh_token=refresh,
                client_id=client_id,
            )
            with lock:
                outcomes.append("ok")
        except OAuthError:
            s.rollback()
            with lock:
                outcomes.append("fail")
        except Exception:
            s.rollback()
            with lock:
                outcomes.append("error")
            raise
        finally:
            s.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futs = [pool.submit(worker), pool.submit(worker)]
        for f in futs:
            f.result(timeout=30)

    assert outcomes.count("ok") == 1, outcomes
    assert outcomes.count("fail") == 1, outcomes

    # Replaying the original refresh again must fail and leave no active family tip.
    db2 = SessionLocal()
    try:
        with pytest.raises(OAuthError):
            oauth_service.refresh_access_token(
                db2,
                grant_type=GRANT_REFRESH_TOKEN,
                refresh_token=refresh,
                client_id=client_id,
            )
    finally:
        db2.close()

    with engine.connect() as conn:
        active = conn.execute(
            text(
                "SELECT COUNT(*) FROM oauth_refresh_sessions "
                "WHERE client_id=:c AND user_id=:u AND revoked_at IS NULL"
            ),
            {"c": client_id, "u": user_id},
        ).scalar_one()
        assert int(active) == 0
