"""Desktop OAuth Authorization Code + PKCE service (Phase 9C-B)."""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import CompanyUser
from app.oauth.audit import record_oauth_audit
from app.oauth.constants import (
    AUDIT_AUTHORIZATION_DENIED,
    AUDIT_AUTHORIZATION_GRANTED,
    AUDIT_AUTHORIZATION_STARTED,
    AUDIT_REFRESH_REPLAY,
    AUDIT_SESSION_REVOKED,
    AUDIT_TOKEN_ISSUED,
    AUDIT_TOKEN_REFRESHED,
    CODE_CHALLENGE_METHOD_S256,
    DEFAULT_ACCESS_TOKEN_MINUTES,
    DEFAULT_AUTH_CODE_TTL_SECONDS,
    DEFAULT_REFRESH_TOKEN_DAYS,
    DESKTOP_JWT_AUD,
    DESKTOP_JWT_ISS,
    ERR_ACCESS_DENIED,
    ERR_INVALID_CLIENT,
    ERR_INVALID_GRANT,
    ERR_INVALID_REQUEST,
    ERR_INVALID_SCOPE,
    ERR_UNAUTHORIZED_CLIENT,
    ERR_UNSUPPORTED_GRANT,
    ERR_UNSUPPORTED_RESPONSE,
    GRANT_AUTHORIZATION_CODE,
    GRANT_REFRESH_TOKEN,
    RESPONSE_TYPE_CODE,
    REVOKE_MEMBERSHIP_CHANGED,
    REVOKE_PASSWORD_CHANGED,
    REVOKE_REFRESH_REPLAY,
    REVOKE_REPLACED,
    REVOKE_SIGN_OUT,
    REVOKE_SIGN_OUT_ALL,
    REVOKE_USER_BLOCKED,
    SCOPE_DESKTOP_LICENSE,
    SUPPORTED_SCOPES,
    TOKEN_TYPE_BEARER,
)
from app.oauth.errors import OAuthError
from app.oauth.models import OAuthAuthorizationCode, OAuthDesktopClient, OAuthRefreshSession
from app.oauth.pkce import (
    generate_authorization_code,
    generate_refresh_token,
    hash_secret,
    validate_code_challenge,
    verify_pkce_s256,
)
from app.security import create_access_token


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _split_scopes(scope: str) -> list[str]:
    return [s for s in (scope or "").split() if s]


def get_enabled_client(db: Session, client_id: str) -> OAuthDesktopClient:
    client = db.execute(
        select(OAuthDesktopClient).where(OAuthDesktopClient.client_id == client_id)
    ).scalar_one_or_none()
    if not client:
        raise OAuthError(ERR_INVALID_CLIENT, description="Unknown client", status_code=401)
    if int(client.enabled) != 1:
        raise OAuthError(ERR_UNAUTHORIZED_CLIENT, description="Client disabled", status_code=401)
    if (client.client_type or "").lower() != "public":
        raise OAuthError(ERR_UNAUTHORIZED_CLIENT, description="Unsupported client type", status_code=401)
    return client


def assert_redirect_uri_allowed(client: OAuthDesktopClient, redirect_uri: str) -> str:
    uri = (redirect_uri or "").strip()
    allowed = [(u or "").strip() for u in (client.redirect_uris or [])]
    if uri not in allowed:
        raise OAuthError(ERR_INVALID_REQUEST, description="redirect_uri mismatch")
    return uri


def assert_scopes_allowed(client: OAuthDesktopClient, scope: str) -> str:
    requested = _split_scopes(scope)
    if not requested:
        raise OAuthError(ERR_INVALID_SCOPE, description="scope required")
    allowed = set(client.allowed_scopes or [])
    for s in requested:
        if s not in SUPPORTED_SCOPES or s not in allowed:
            raise OAuthError(ERR_INVALID_SCOPE, description=f"scope not allowed: {s}")
    return " ".join(sorted(set(requested)))


def validate_authorize_params(
    db: Session,
    *,
    response_type: str | None,
    client_id: str | None,
    redirect_uri: str | None,
    scope: str | None,
    state: str | None,
    code_challenge: str | None,
    code_challenge_method: str | None,
) -> tuple[OAuthDesktopClient, str, str, str, str]:
    if not client_id:
        raise OAuthError(ERR_INVALID_REQUEST, description="client_id required")
    if not redirect_uri:
        raise OAuthError(ERR_INVALID_REQUEST, description="redirect_uri required")
    if not state or not str(state).strip():
        raise OAuthError(ERR_INVALID_REQUEST, description="state required")
    if not code_challenge:
        raise OAuthError(ERR_INVALID_REQUEST, description="code_challenge required")
    if (code_challenge_method or "").upper() != CODE_CHALLENGE_METHOD_S256:
        raise OAuthError(ERR_INVALID_REQUEST, description="code_challenge_method must be S256")
    if not validate_code_challenge(code_challenge):
        raise OAuthError(ERR_INVALID_REQUEST, description="invalid code_challenge")
    if (response_type or "") != RESPONSE_TYPE_CODE:
        raise OAuthError(ERR_UNSUPPORTED_RESPONSE, description="response_type must be code")

    client = get_enabled_client(db, client_id)
    uri = assert_redirect_uri_allowed(client, redirect_uri)
    normalized_scope = assert_scopes_allowed(client, scope or "")
    return client, uri, normalized_scope, str(state).strip(), code_challenge


def spa_authorize_url(settings: Settings, query: dict[str, str]) -> str:
    base = (settings.public_app_url or "").rstrip("/")
    return f"{base}/oauth/authorize?{urlencode(query)}"


def build_code_redirect(redirect_uri: str, *, code: str, state: str) -> str:
    sep = "&" if "?" in redirect_uri else "?"
    return f"{redirect_uri}{sep}{urlencode({'code': code, 'state': state})}"


def _access_minutes(settings: Settings) -> int:
    minutes = int(
        getattr(settings, "oauth_desktop_access_token_minutes", None) or DEFAULT_ACCESS_TOKEN_MINUTES
    )
    return max(15, min(60, minutes))


def _auth_code_ttl_seconds(settings: Settings) -> int:
    ttl = int(
        getattr(settings, "oauth_authorization_code_ttl_seconds", None) or DEFAULT_AUTH_CODE_TTL_SECONDS
    )
    return max(60, min(300, ttl))


def _refresh_ttl_days(settings: Settings) -> int:
    days = int(
        getattr(settings, "oauth_desktop_refresh_token_days", None) or DEFAULT_REFRESH_TOKEN_DAYS
    )
    return max(1, min(365, days))


def create_desktop_access_token(
    *,
    user_id: int,
    company_id: int,
    client_id: str,
    scope: str,
    settings: Settings | None = None,
) -> tuple[str, int]:
    settings = settings or get_settings()
    minutes = _access_minutes(settings)
    now = _utcnow()
    token = create_access_token(
        str(user_id),
        {
            "company_id": int(company_id),
            "iat": int(now.timestamp()),
            "iss": DESKTOP_JWT_ISS,
            "aud": DESKTOP_JWT_AUD,
            "client_id": client_id,
            "scope": scope,
            "amr": ["oauth_pkce"],
        },
        expires_minutes=minutes,
    )
    return token, minutes * 60


def issue_authorization_code(
    db: Session,
    *,
    user: CompanyUser,
    client: OAuthDesktopClient,
    redirect_uri: str,
    scope: str,
    state: str,
    code_challenge: str,
    settings: Settings | None = None,
) -> str:
    settings = settings or get_settings()
    if bool(user.is_blocked):
        raise OAuthError(ERR_ACCESS_DENIED, description="User blocked", status_code=403)

    raw = generate_authorization_code()
    db.add(
        OAuthAuthorizationCode(
            code_hash=hash_secret(raw),
            user_id=int(user.id),
            company_id=int(user.company_id),
            client_id=client.client_id,
            redirect_uri=redirect_uri,
            scope=scope,
            code_challenge=code_challenge,
            code_challenge_method=CODE_CHALLENGE_METHOD_S256,
            state=state,
            expires_at=_utcnow() + timedelta(seconds=_auth_code_ttl_seconds(settings)),
        )
    )
    record_oauth_audit(
        db,
        event_type=AUDIT_AUTHORIZATION_GRANTED,
        success=True,
        user_id=int(user.id),
        company_id=int(user.company_id),
        client_id=client.client_id,
        meta={"scope": scope},
    )
    db.flush()
    return raw


def deny_authorization(
    db: Session,
    *,
    user: CompanyUser | None,
    client_id: str | None,
    reason: str = "user_denied",
) -> None:
    record_oauth_audit(
        db,
        event_type=AUDIT_AUTHORIZATION_DENIED,
        success=False,
        user_id=int(user.id) if user else None,
        company_id=int(user.company_id) if user else None,
        client_id=client_id,
        error_code=ERR_ACCESS_DENIED,
        meta={"reason": reason},
    )


def record_authorization_started(
    db: Session,
    *,
    client_id: str,
    meta: dict[str, Any] | None = None,
) -> None:
    record_oauth_audit(
        db,
        event_type=AUDIT_AUTHORIZATION_STARTED,
        success=True,
        client_id=client_id,
        meta=meta,
    )


def _consume_authorization_code(
    db: Session,
    *,
    code: str,
    client_id: str,
    redirect_uri: str,
    code_verifier: str,
) -> OAuthAuthorizationCode:
    if not code or not code_verifier:
        raise OAuthError(ERR_INVALID_REQUEST, description="code and code_verifier required")

    row = db.execute(
        select(OAuthAuthorizationCode)
        .where(OAuthAuthorizationCode.code_hash == hash_secret(code))
        .with_for_update()
    ).scalar_one_or_none()
    if not row:
        raise OAuthError(ERR_INVALID_GRANT, description="Invalid authorization code")
    if row.used_at is not None:
        raise OAuthError(ERR_INVALID_GRANT, description="Authorization code already used")
    if _aware(row.expires_at) < _utcnow():
        raise OAuthError(ERR_INVALID_GRANT, description="Authorization code expired")
    if row.client_id != client_id:
        raise OAuthError(ERR_INVALID_GRANT, description="client_id mismatch")
    if (row.redirect_uri or "").strip() != (redirect_uri or "").strip():
        raise OAuthError(ERR_INVALID_GRANT, description="redirect_uri mismatch")
    if not verify_pkce_s256(code_verifier=code_verifier, code_challenge=row.code_challenge):
        raise OAuthError(ERR_INVALID_GRANT, description="PKCE verification failed")

    row.used_at = _utcnow()
    db.flush()
    return row


def _create_refresh_session(
    db: Session,
    *,
    user_id: int,
    company_id: int,
    client_id: str,
    scope: str,
    family_id: uuid.UUID | None = None,
    settings: Settings | None = None,
) -> tuple[str, OAuthRefreshSession]:
    settings = settings or get_settings()
    raw = generate_refresh_token()
    session = OAuthRefreshSession(
        family_id=family_id or uuid.uuid4(),
        user_id=user_id,
        company_id=company_id,
        client_id=client_id,
        scope=scope,
        token_hash=hash_secret(raw),
        expires_at=_utcnow() + timedelta(days=_refresh_ttl_days(settings)),
    )
    db.add(session)
    db.flush()
    return raw, session


def _load_user_for_token(db: Session, user_id: int, company_id: int) -> CompanyUser:
    user = db.get(CompanyUser, int(user_id))
    if not user:
        raise OAuthError(ERR_INVALID_GRANT, description="User not found")
    if bool(user.is_blocked):
        raise OAuthError(ERR_INVALID_GRANT, description="User blocked", status_code=403)
    if int(user.company_id) != int(company_id):
        raise OAuthError(ERR_INVALID_GRANT, description="Company membership changed")
    return user


def _revoke_family(db: Session, family_id: uuid.UUID, *, reason: str) -> int:
    result = db.execute(
        update(OAuthRefreshSession)
        .where(
            OAuthRefreshSession.family_id == family_id,
            OAuthRefreshSession.revoked_at.is_(None),
        )
        .values(revoked_at=_utcnow(), revoke_reason=reason)
    )
    return int(result.rowcount or 0)


def exchange_authorization_code(
    db: Session,
    *,
    grant_type: str,
    code: str,
    client_id: str,
    redirect_uri: str,
    code_verifier: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    if grant_type != GRANT_AUTHORIZATION_CODE:
        raise OAuthError(ERR_UNSUPPORTED_GRANT, description="unsupported grant_type")

    client = get_enabled_client(db, client_id)
    assert_redirect_uri_allowed(client, redirect_uri)
    row = _consume_authorization_code(
        db,
        code=code,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_verifier=code_verifier,
    )
    user = _load_user_for_token(db, row.user_id, row.company_id)
    access, expires_in = create_desktop_access_token(
        user_id=int(user.id),
        company_id=int(user.company_id),
        client_id=client.client_id,
        scope=row.scope,
        settings=settings,
    )
    refresh, _ = _create_refresh_session(
        db,
        user_id=int(user.id),
        company_id=int(user.company_id),
        client_id=client.client_id,
        scope=row.scope,
        settings=settings,
    )
    record_oauth_audit(
        db,
        event_type=AUDIT_TOKEN_ISSUED,
        success=True,
        user_id=int(user.id),
        company_id=int(user.company_id),
        client_id=client.client_id,
        meta={"grant": GRANT_AUTHORIZATION_CODE, "scope": row.scope},
    )
    db.commit()
    return {
        "access_token": access,
        "token_type": TOKEN_TYPE_BEARER,
        "expires_in": expires_in,
        "refresh_token": refresh,
        "scope": row.scope,
    }


def refresh_access_token(
    db: Session,
    *,
    grant_type: str,
    refresh_token: str,
    client_id: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    if grant_type != GRANT_REFRESH_TOKEN:
        raise OAuthError(ERR_UNSUPPORTED_GRANT, description="unsupported grant_type")
    if not refresh_token:
        raise OAuthError(ERR_INVALID_REQUEST, description="refresh_token required")

    client = get_enabled_client(db, client_id)
    row = db.execute(
        select(OAuthRefreshSession)
        .where(OAuthRefreshSession.token_hash == hash_secret(refresh_token))
        .with_for_update()
    ).scalar_one_or_none()
    if not row:
        raise OAuthError(ERR_INVALID_GRANT, description="Invalid refresh token")
    if row.client_id != client.client_id:
        raise OAuthError(ERR_INVALID_GRANT, description="client_id mismatch")

    if row.revoked_at is not None or row.replaced_by_id is not None:
        n = _revoke_family(db, row.family_id, reason=REVOKE_REFRESH_REPLAY)
        record_oauth_audit(
            db,
            event_type=AUDIT_REFRESH_REPLAY,
            success=False,
            user_id=int(row.user_id),
            company_id=int(row.company_id),
            client_id=client.client_id,
            error_code=ERR_INVALID_GRANT,
            meta={"family_revoked": n},
        )
        db.commit()
        raise OAuthError(ERR_INVALID_GRANT, description="Refresh token replay detected")

    if _aware(row.expires_at) < _utcnow():
        row.revoked_at = _utcnow()
        row.revoke_reason = "expired"
        db.commit()
        raise OAuthError(ERR_INVALID_GRANT, description="Refresh token expired")

    try:
        user = _load_user_for_token(db, row.user_id, row.company_id)
    except OAuthError:
        _revoke_family(db, row.family_id, reason=REVOKE_MEMBERSHIP_CHANGED)
        db.commit()
        raise

    access, expires_in = create_desktop_access_token(
        user_id=int(user.id),
        company_id=int(user.company_id),
        client_id=client.client_id,
        scope=row.scope,
        settings=settings,
    )
    new_raw, new_row = _create_refresh_session(
        db,
        user_id=int(user.id),
        company_id=int(user.company_id),
        client_id=client.client_id,
        scope=row.scope,
        family_id=row.family_id,
        settings=settings,
    )
    row.replaced_by_id = new_row.id
    row.revoked_at = _utcnow()
    row.revoke_reason = REVOKE_REPLACED
    row.last_used_at = _utcnow()
    record_oauth_audit(
        db,
        event_type=AUDIT_TOKEN_REFRESHED,
        success=True,
        user_id=int(user.id),
        company_id=int(user.company_id),
        client_id=client.client_id,
        meta={"scope": row.scope},
    )
    db.commit()
    return {
        "access_token": access,
        "token_type": TOKEN_TYPE_BEARER,
        "expires_in": expires_in,
        "refresh_token": new_raw,
        "scope": row.scope,
    }


def revoke_refresh_token(
    db: Session,
    *,
    token: str,
    client_id: str,
    user_id: int | None = None,
) -> int:
    client = get_enabled_client(db, client_id)
    row = db.execute(
        select(OAuthRefreshSession).where(OAuthRefreshSession.token_hash == hash_secret(token))
    ).scalar_one_or_none()
    if not row:
        return 0
    if row.client_id != client.client_id:
        return 0
    if user_id is not None and int(row.user_id) != int(user_id):
        return 0
    n = _revoke_family(db, row.family_id, reason=REVOKE_SIGN_OUT)
    record_oauth_audit(
        db,
        event_type=AUDIT_SESSION_REVOKED,
        success=True,
        user_id=int(row.user_id),
        company_id=int(row.company_id),
        client_id=client.client_id,
        meta={"reason": REVOKE_SIGN_OUT, "revoked": n},
    )
    db.commit()
    return n


def revoke_all_user_sessions(
    db: Session,
    *,
    user_id: int,
    reason: str,
    client_id: str | None = None,
    commit: bool = True,
) -> int:
    stmt = update(OAuthRefreshSession).where(
        OAuthRefreshSession.user_id == int(user_id),
        OAuthRefreshSession.revoked_at.is_(None),
    )
    if client_id:
        stmt = stmt.where(OAuthRefreshSession.client_id == client_id)
    result = db.execute(stmt.values(revoked_at=_utcnow(), revoke_reason=reason))
    n = int(result.rowcount or 0)
    if n:
        record_oauth_audit(
            db,
            event_type=AUDIT_SESSION_REVOKED,
            success=True,
            user_id=int(user_id),
            client_id=client_id,
            meta={"reason": reason, "revoked": n},
        )
    if commit:
        db.commit()
    return n


def revoke_on_password_change(db: Session, user_id: int) -> int:
    return revoke_all_user_sessions(
        db, user_id=user_id, reason=REVOKE_PASSWORD_CHANGED, commit=False
    )


def revoke_on_user_blocked(db: Session, user_id: int) -> int:
    return revoke_all_user_sessions(db, user_id=user_id, reason=REVOKE_USER_BLOCKED, commit=False)


def revoke_all_for_client_user(db: Session, *, user_id: int, client_id: str) -> int:
    return revoke_all_user_sessions(
        db, user_id=user_id, client_id=client_id, reason=REVOKE_SIGN_OUT_ALL, commit=True
    )


def new_oauth_state() -> str:
    return secrets.token_urlsafe(24)


DEFAULT_SCOPE = SCOPE_DESKTOP_LICENSE
