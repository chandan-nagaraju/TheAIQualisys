"""Phase 9C-B: Desktop OAuth Authorization Code + PKCE foundation tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import HTTPException
from jose import jwt

from app.config import Settings
from app.oauth import service as oauth_service
from app.oauth.constants import (
    ERR_ACCESS_DENIED,
    ERR_INVALID_CLIENT,
    ERR_INVALID_REQUEST,
    ERR_INVALID_SCOPE,
    ERR_UNAUTHORIZED_CLIENT,
    ERR_UNSUPPORTED_RESPONSE,
    SCOPE_DESKTOP_LICENSE,
)
from app.oauth.errors import OAuthError
from app.oauth.pkce import (
    challenge_s256,
    generate_authorization_code,
    generate_code_verifier,
    generate_refresh_token,
    hash_secret,
    validate_code_challenge,
    validate_code_verifier,
    verify_pkce_s256,
)
from app.oauth.rate_limit import check_oauth_rate_limit, clear_oauth_rate_limit_buckets
from app.security import create_access_token, create_admin_token, decode_access_token


def _settings(**kwargs) -> Settings:
    base = dict(
        jwt_secret="test-jwt-secret-phase9cb",
        admin_jwt_secret="test-admin-jwt-secret-phase9cb",
        oauth_desktop_access_token_minutes=30,
        oauth_desktop_refresh_token_days=90,
        oauth_authorization_code_ttl_seconds=180,
        public_app_url="https://staging.example.test",
        access_token_expire_minutes=60 * 24 * 7,
        enable_desktop_licensing=False,
    )
    base.update(kwargs)
    return Settings(**base)


def _client(**kwargs):
    defaults = dict(
        client_id="qr-code-desktop-staging",
        client_name="QR Code Desktop",
        client_type="public",
        redirect_uris=["aiqualisys-qr://oauth/callback"],
        allowed_scopes=[SCOPE_DESKTOP_LICENSE],
        enabled=1,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _user(**kwargs):
    defaults = dict(id=7, company_id=3, is_blocked=0, email="user@example.test")
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_pkce_s256_roundtrip():
    verifier = generate_code_verifier()
    assert validate_code_verifier(verifier)
    challenge = challenge_s256(verifier)
    assert validate_code_challenge(challenge)
    assert verify_pkce_s256(code_verifier=verifier, code_challenge=challenge)


def test_pkce_rejects_invalid_verifier():
    assert not validate_code_verifier("short")
    assert not verify_pkce_s256(code_verifier="plain", code_challenge="x" * 43)


def test_secrets_are_hashed():
    raw = generate_authorization_code()
    assert hash_secret(raw) != raw
    assert len(hash_secret(raw)) == 64
    assert hash_secret(generate_refresh_token()) != generate_refresh_token()


def test_desktop_access_token_short_lived_compatible():
    settings = _settings()
    with patch("app.oauth.service.get_settings", return_value=settings), patch(
        "app.security.get_settings", return_value=settings
    ):
        token, expires_in = oauth_service.create_desktop_access_token(
            user_id=7,
            company_id=3,
            client_id="qr-code-desktop-staging",
            scope=SCOPE_DESKTOP_LICENSE,
            settings=settings,
        )
        payload = decode_access_token(token)
    assert 15 * 60 <= expires_in <= 60 * 60
    assert payload is not None
    assert payload["typ"] == "company"
    assert payload["sub"] == "7"
    assert int(payload["company_id"]) == 3
    assert payload["aud"] == "aiqualisys-desktop"
    assert payload["iss"] == "aiqualisys"
    assert "license_key" not in payload
    assert "fingerprint" not in payload


def test_spa_token_default_lifetime_unchanged():
    settings = _settings()
    with patch("app.security.get_settings", return_value=settings):
        token = create_access_token("9", {"company_id": 1})
        payload = decode_access_token(token)
    assert payload["typ"] == "company"
    assert payload.get("aud") != "aiqualisys-desktop"
    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    assert timedelta(days=6) < (exp - datetime.now(timezone.utc)) < timedelta(days=8)


def test_admin_token_cannot_be_minted_via_desktop_helper():
    settings = _settings()
    with patch("app.security.get_settings", return_value=settings):
        admin = create_admin_token("1")
        assert jwt.get_unverified_claims(admin)["typ"] == "platform_admin"
        with patch("app.oauth.service.get_settings", return_value=settings):
            token, _ = oauth_service.create_desktop_access_token(
                user_id=1,
                company_id=1,
                client_id="c",
                scope=SCOPE_DESKTOP_LICENSE,
                settings=settings,
            )
            assert decode_access_token(token)["typ"] == "company"


def test_unknown_and_disabled_client():
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = None
    with pytest.raises(OAuthError) as exc:
        oauth_service.get_enabled_client(db, "missing")
    assert exc.value.error == ERR_INVALID_CLIENT

    db.execute.return_value.scalar_one_or_none.return_value = _client(enabled=0)
    with pytest.raises(OAuthError) as exc2:
        oauth_service.get_enabled_client(db, "qr-code-desktop-staging")
    assert exc2.value.error == ERR_UNAUTHORIZED_CLIENT


def test_exact_redirect_uri_and_scope():
    client = _client()
    with pytest.raises(OAuthError) as exc:
        oauth_service.assert_redirect_uri_allowed(client, "aiqualisys-qr://oauth/other")
    assert exc.value.error == ERR_INVALID_REQUEST
    assert oauth_service.assert_redirect_uri_allowed(client, "aiqualisys-qr://oauth/callback")

    with pytest.raises(OAuthError) as exc2:
        oauth_service.assert_scopes_allowed(client, "admin")
    assert exc2.value.error == ERR_INVALID_SCOPE
    assert oauth_service.assert_scopes_allowed(client, SCOPE_DESKTOP_LICENSE) == SCOPE_DESKTOP_LICENSE


def test_authorize_requires_pkce_s256_and_code_response():
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = _client()
    with pytest.raises(OAuthError) as exc:
        oauth_service.validate_authorize_params(
            db,
            response_type="code",
            client_id="qr-code-desktop-staging",
            redirect_uri="aiqualisys-qr://oauth/callback",
            scope=SCOPE_DESKTOP_LICENSE,
            state="abc",
            code_challenge=None,
            code_challenge_method="S256",
        )
    assert exc.value.error == ERR_INVALID_REQUEST

    verifier = generate_code_verifier()
    with pytest.raises(OAuthError) as exc2:
        oauth_service.validate_authorize_params(
            db,
            response_type="code",
            client_id="qr-code-desktop-staging",
            redirect_uri="aiqualisys-qr://oauth/callback",
            scope=SCOPE_DESKTOP_LICENSE,
            state="abc",
            code_challenge=challenge_s256(verifier),
            code_challenge_method="plain",
        )
    assert exc2.value.error == ERR_INVALID_REQUEST

    with pytest.raises(OAuthError) as exc3:
        oauth_service.validate_authorize_params(
            db,
            response_type="token",
            client_id="qr-code-desktop-staging",
            redirect_uri="aiqualisys-qr://oauth/callback",
            scope=SCOPE_DESKTOP_LICENSE,
            state="s",
            code_challenge=challenge_s256(verifier),
            code_challenge_method="S256",
        )
    assert exc3.value.error == ERR_UNSUPPORTED_RESPONSE


def test_successful_authorize_params():
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = _client()
    challenge = challenge_s256(generate_code_verifier())
    client, uri, scope, state, ch = oauth_service.validate_authorize_params(
        db,
        response_type="code",
        client_id="qr-code-desktop-staging",
        redirect_uri="aiqualisys-qr://oauth/callback",
        scope=SCOPE_DESKTOP_LICENSE,
        state="xyz",
        code_challenge=challenge,
        code_challenge_method="S256",
    )
    assert client.client_id == "qr-code-desktop-staging"
    assert uri == "aiqualisys-qr://oauth/callback"
    assert scope == SCOPE_DESKTOP_LICENSE
    assert state == "xyz"
    assert ch == challenge


def test_redirect_builders_never_include_tokens():
    url = oauth_service.build_code_redirect(
        "aiqualisys-qr://oauth/callback", code="AUTHCODE", state="st"
    )
    qs = parse_qs(urlparse(url).query)
    assert qs["code"] == ["AUTHCODE"]
    assert qs["state"] == ["st"]
    assert "access_token" not in qs
    assert "refresh_token" not in qs

    spa = oauth_service.spa_authorize_url(_settings(), {"client_id": "c", "state": "s"})
    assert spa.startswith("https://staging.example.test/oauth/authorize?")
    assert "access_token" not in spa


def test_blocked_user_cannot_receive_code():
    db = MagicMock()
    with pytest.raises(OAuthError) as exc:
        oauth_service.issue_authorization_code(
            db,
            user=_user(is_blocked=1),
            client=_client(),
            redirect_uri="aiqualisys-qr://oauth/callback",
            scope=SCOPE_DESKTOP_LICENSE,
            state="s",
            code_challenge=challenge_s256(generate_code_verifier()),
            settings=_settings(),
        )
    assert exc.value.error == ERR_ACCESS_DENIED


def test_audit_sensitive_keys_defined():
    from app.oauth.audit import SENSITIVE_META_KEYS

    for key in ("access_token", "refresh_token", "code", "code_verifier"):
        assert key in SENSITIVE_META_KEYS


def test_oauth_rate_limit_bucket():
    clear_oauth_rate_limit_buckets()
    for _ in range(3):
        check_oauth_rate_limit(scope="t", key="k", limit=3)
    with pytest.raises(HTTPException) as exc:
        check_oauth_rate_limit(scope="t", key="k", limit=3)
    assert exc.value.status_code == 429
    clear_oauth_rate_limit_buckets()


def test_spa_login_token_path_regression():
    settings = _settings()
    with patch("app.security.get_settings", return_value=settings):
        tok = create_access_token("42", {"company_id": 99})
        p = decode_access_token(tok)
    assert p["typ"] == "company"
    assert int(p["company_id"]) == 99


# ---------------------------------------------------------------------------
# Phase 9C-D hardening: admin impersonation must not authorize desktop OAuth
# ---------------------------------------------------------------------------


def test_get_oauth_company_user_allows_direct_login():
    from app.deps import get_oauth_company_user

    user = _user()
    assert get_oauth_company_user(user=user, impersonated=False) is user


def test_get_oauth_company_user_rejects_admin_impersonation():
    from app.deps import get_oauth_company_user
    from app.oauth.constants import ERR_ACCESS_DENIED
    from app.oauth.errors import OAuthError

    with pytest.raises(OAuthError) as exc:
        get_oauth_company_user(user=_user(), impersonated=True)
    assert exc.value.error == ERR_ACCESS_DENIED
    assert exc.value.status_code == 403
    assert "direct company login" in (exc.value.description or "").lower()


def test_impersonation_claim_detected_but_spa_auth_still_works(monkeypatch):
    """Admin impersonation remains valid for company SPA auth; only OAuth blocks it."""
    from app.deps import company_impersonated_by_admin, get_current_company_user, impersonated_by_admin_from_token
    from jose import jwt as jose_jwt
    from app.security import create_access_token, create_admin_token, decode_access_token
    from fastapi.security import HTTPAuthorizationCredentials

    settings = _settings()
    with patch("app.security.get_settings", return_value=settings):
        normal = create_access_token("7", {"company_id": 3})
        imp = create_access_token("7", {"company_id": 3, "impersonated_by_admin": True})
        admin = create_admin_token("1")

        assert impersonated_by_admin_from_token(normal) is False
        assert impersonated_by_admin_from_token(imp) is True
        assert jose_jwt.get_unverified_claims(admin).get("typ") == "platform_admin"
        # Admin JWTs use a different secret/typ and must not look like company impersonation.
        assert impersonated_by_admin_from_token(admin) is False

        user = _user()
        db = MagicMock()
        db.get.return_value = user
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=imp)
        # Impersonated company JWT still resolves as a company user for SPA/support paths.
        assert get_current_company_user(creds=creds, db=db) is user
        assert company_impersonated_by_admin(creds=creds) is True


def _oauth_test_client(monkeypatch, *, impersonated: bool, user=None):
    from fastapi.testclient import TestClient

    from app.deps import company_impersonated_by_admin, get_current_company_user, get_db_session
    from app.main import create_app

    user = user or _user()
    app = create_app()
    app.state.startup_complete = True
    app.state.startup_status = "ok"
    app.dependency_overrides[get_current_company_user] = lambda: user
    app.dependency_overrides[company_impersonated_by_admin] = lambda: impersonated
    app.dependency_overrides[get_db_session] = lambda: MagicMock()
    return TestClient(app), user


def _preview_query() -> dict[str, str]:
    from app.oauth.pkce import challenge_s256, generate_code_verifier
    from app.oauth.constants import SCOPE_DESKTOP_LICENSE

    verifier = generate_code_verifier()
    return {
        "response_type": "code",
        "client_id": "qr-code-desktop-staging",
        "redirect_uri": "aiqualisys-qr://oauth/callback",
        "scope": SCOPE_DESKTOP_LICENSE,
        "state": "desktop-state-abc",
        "code_challenge": challenge_s256(verifier),
        "code_challenge_method": "S256",
    }


def test_http_direct_company_user_can_preview_desktop_oauth(monkeypatch):
    client, user = _oauth_test_client(monkeypatch, impersonated=False)
    q = _preview_query()
    fake_client = _client()
    with patch(
        "app.oauth.service.validate_authorize_params",
        return_value=(fake_client, q["redirect_uri"], q["scope"], q["state"], q["code_challenge"]),
    ):
        r = client.get("/oauth/authorize/preview", params=q)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["client_id"] == fake_client.client_id
    assert body["state"] == q["state"]


def test_http_admin_impersonated_user_cannot_preview_or_consent(monkeypatch):
    from app.oauth.constants import ERR_ACCESS_DENIED, SCOPE_DESKTOP_LICENSE
    from app.oauth.pkce import challenge_s256, generate_code_verifier

    client, _user_obj = _oauth_test_client(monkeypatch, impersonated=True)
    q = _preview_query()
    r = client.get("/oauth/authorize/preview", params=q)
    assert r.status_code == 403
    assert r.json()["error"] == ERR_ACCESS_DENIED

    verifier = generate_code_verifier()
    payload = {
        "client_id": "qr-code-desktop-staging",
        "redirect_uri": "aiqualisys-qr://oauth/callback",
        "scope": SCOPE_DESKTOP_LICENSE,
        "state": "s",
        "code_challenge": challenge_s256(verifier),
        "code_challenge_method": "S256",
        "decision": "approve",
    }
    r2 = client.post("/oauth/authorize/consent", json=payload)
    assert r2.status_code == 403
    assert r2.json()["error"] == ERR_ACCESS_DENIED

    r3 = client.post("/oauth/revoke", json={"client_id": "qr-code-desktop-staging", "revoke_all": True})
    assert r3.status_code == 403
    assert r3.json()["error"] == ERR_ACCESS_DENIED


def test_http_platform_admin_token_cannot_authorize_desktop_oauth(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.security import create_admin_token

    settings = _settings()
    with patch("app.security.get_settings", return_value=settings):
        admin_jwt = create_admin_token("1")

    app = create_app()
    app.state.startup_complete = True
    app.state.startup_status = "ok"
    client = TestClient(app)
    r = client.get(
        "/oauth/authorize/preview",
        params=_preview_query(),
        headers={"Authorization": f"Bearer {admin_jwt}"},
    )
    assert r.status_code == 401


def test_http_direct_user_consent_issues_code_redirect(monkeypatch):
    from app.oauth.constants import SCOPE_DESKTOP_LICENSE
    from app.oauth.pkce import challenge_s256, generate_code_verifier

    client, user = _oauth_test_client(monkeypatch, impersonated=False)
    verifier = generate_code_verifier()
    challenge = challenge_s256(verifier)
    fake_client = _client()
    with patch(
        "app.oauth.service.validate_authorize_params",
        return_value=(fake_client, "aiqualisys-qr://oauth/callback", SCOPE_DESKTOP_LICENSE, "st", challenge),
    ), patch(
        "app.oauth.service.issue_authorization_code",
        return_value="AUTHCODE123",
    ):
        r = client.post(
            "/oauth/authorize/consent",
            json={
                "client_id": fake_client.client_id,
                "redirect_uri": "aiqualisys-qr://oauth/callback",
                "scope": SCOPE_DESKTOP_LICENSE,
                "state": "st",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "decision": "approve",
            },
        )
    assert r.status_code == 200, r.text
    redirect_to = r.json()["redirect_to"]
    assert "code=AUTHCODE123" in redirect_to
    assert "state=st" in redirect_to
    assert "access_token" not in redirect_to
    assert "refresh_token" not in redirect_to
