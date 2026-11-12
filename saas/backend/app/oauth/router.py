"""OAuth HTTP routes for desktop Authorization Code + PKCE."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.deps import get_db_session, get_oauth_company_user
from app.models import CompanyUser
from app.oauth import service as oauth_service
from app.oauth.constants import (
    ERR_ACCESS_DENIED,
    ERR_INVALID_CLIENT,
    ERR_INVALID_REQUEST,
    ERR_UNSUPPORTED_GRANT,
    GRANT_AUTHORIZATION_CODE,
    GRANT_REFRESH_TOKEN,
)
from app.oauth.errors import OAuthError, oauth_error_response, redirect_with_oauth_error
from app.oauth.rate_limit import check_oauth_rate_limit
from app.oauth.schemas import (
    OAuthAuthorizePreview,
    OAuthConsentRequest,
    OAuthConsentResponse,
    OAuthRevokeRequest,
    OAuthRevokeResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["oauth-desktop"])


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    if request.client and request.client.host:
        return request.client.host[:64]
    return "unknown"


@router.get("/oauth/authorize")
def oauth_authorize(
    request: Request,
    db: Session = Depends(get_db_session),
    response_type: str | None = Query(None),
    client_id: str | None = Query(None),
    redirect_uri: str | None = Query(None),
    scope: str | None = Query(None),
    state: str | None = Query(None),
    code_challenge: str | None = Query(None),
    code_challenge_method: str | None = Query(None),
):
    """Validate authorize request; redirect browser to SPA consent UI (never JWT)."""
    check_oauth_rate_limit(scope="oauth_authorize_ip", key=_client_ip(request), limit=30)
    settings = get_settings()
    try:
        client, uri, normalized_scope, st, challenge = oauth_service.validate_authorize_params(
            db,
            response_type=response_type,
            client_id=client_id,
            redirect_uri=redirect_uri,
            scope=scope,
            state=state,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
        )
        oauth_service.record_authorization_started(
            db, client_id=client.client_id, meta={"scope": normalized_scope}
        )
        db.commit()
    except OAuthError as exc:
        db.rollback()
        if client_id and redirect_uri and exc.error != ERR_INVALID_CLIENT:
            try:
                client = oauth_service.get_enabled_client(db, client_id)
                oauth_service.assert_redirect_uri_allowed(client, redirect_uri)
                return redirect_with_oauth_error(
                    redirect_uri,
                    error=exc.error,
                    state=state,
                    description=exc.description,
                )
            except OAuthError:
                pass
        return oauth_error_response(exc)

    q = {
        "response_type": "code",
        "client_id": client.client_id,
        "redirect_uri": uri,
        "scope": normalized_scope,
        "state": st,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return RedirectResponse(url=oauth_service.spa_authorize_url(settings, q), status_code=302)


@router.get("/oauth/authorize/preview", response_model=OAuthAuthorizePreview)
def oauth_authorize_preview(
    request: Request,
    db: Session = Depends(get_db_session),
    user: CompanyUser = Depends(get_oauth_company_user),
    response_type: str | None = Query(None),
    client_id: str | None = Query(None),
    redirect_uri: str | None = Query(None),
    scope: str | None = Query(None),
    state: str | None = Query(None),
    code_challenge: str | None = Query(None),
    code_challenge_method: str | None = Query(None),
):
    """Authenticated preview for SPA consent page (no code issued).

    Rejects admin-impersonated company sessions — desktop OAuth requires a direct login.
    """
    check_oauth_rate_limit(scope="oauth_preview_user", key=str(user.id), limit=60)
    try:
        client, uri, normalized_scope, st, _ch = oauth_service.validate_authorize_params(
            db,
            response_type=response_type,
            client_id=client_id,
            redirect_uri=redirect_uri,
            scope=scope,
            state=state,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
        )
    except OAuthError as exc:
        return oauth_error_response(exc)
    return OAuthAuthorizePreview(
        client_id=client.client_id,
        client_name=client.client_name,
        redirect_uri=uri,
        scope=normalized_scope,
        state=st,
        code_challenge_method="S256",
    )


@router.post("/oauth/authorize/consent", response_model=OAuthConsentResponse)
def oauth_authorize_consent(
    body: OAuthConsentRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    user: CompanyUser = Depends(get_oauth_company_user),
):
    """Approve/deny desktop access. Returns redirect_to with authorization code only.

    Rejects admin-impersonated company sessions — cannot mint a desktop session via impersonation.
    """
    check_oauth_rate_limit(scope="oauth_consent_user", key=str(user.id), limit=20)
    decision = (body.decision or "").strip().lower()
    try:
        client, uri, normalized_scope, st, challenge = oauth_service.validate_authorize_params(
            db,
            response_type="code",
            client_id=body.client_id,
            redirect_uri=body.redirect_uri,
            scope=body.scope,
            state=body.state,
            code_challenge=body.code_challenge,
            code_challenge_method=body.code_challenge_method,
        )
        if decision in {"deny", "denied"}:
            oauth_service.deny_authorization(
                db, user=user, client_id=client.client_id, reason="user_denied"
            )
            db.commit()
            err_redirect = redirect_with_oauth_error(
                uri,
                error=ERR_ACCESS_DENIED,
                state=st,
                description="The user denied the request",
            )
            return OAuthConsentResponse(redirect_to=str(err_redirect.headers["location"]))
        if decision not in {"approve", "approved", "allow"}:
            raise OAuthError(ERR_INVALID_REQUEST, description="decision must be approve or deny")

        code = oauth_service.issue_authorization_code(
            db,
            user=user,
            client=client,
            redirect_uri=uri,
            scope=normalized_scope,
            state=st,
            code_challenge=challenge,
        )
        db.commit()
        return OAuthConsentResponse(
            redirect_to=oauth_service.build_code_redirect(uri, code=code, state=st)
        )
    except OAuthError as exc:
        db.rollback()
        return oauth_error_response(exc)


@router.post("/oauth/token")
async def oauth_token(request: Request, db: Session = Depends(get_db_session)):
    """Token endpoint: authorization_code (+ PKCE) or refresh_token."""
    check_oauth_rate_limit(scope="oauth_token_ip", key=_client_ip(request), limit=60)
    ctype = (request.headers.get("content-type") or "").lower()
    data: dict[str, str] = {}
    try:
        if "application/json" in ctype:
            raw = await request.json()
            if isinstance(raw, dict):
                data = {str(k): "" if v is None else str(v) for k, v in raw.items()}
        else:
            form = await request.form()
            data = {str(k): str(v) for k, v in form.items()}
    except Exception:
        return oauth_error_response(
            OAuthError(ERR_INVALID_REQUEST, description="Malformed token request")
        )

    grant_type = (data.get("grant_type") or "").strip()
    client_id = (data.get("client_id") or "").strip()
    try:
        if grant_type == GRANT_AUTHORIZATION_CODE:
            result = oauth_service.exchange_authorization_code(
                db,
                grant_type=grant_type,
                code=data.get("code") or "",
                client_id=client_id,
                redirect_uri=data.get("redirect_uri") or "",
                code_verifier=data.get("code_verifier") or "",
            )
        elif grant_type == GRANT_REFRESH_TOKEN:
            result = oauth_service.refresh_access_token(
                db,
                grant_type=grant_type,
                refresh_token=data.get("refresh_token") or "",
                client_id=client_id,
            )
        else:
            raise OAuthError(ERR_UNSUPPORTED_GRANT, description="unsupported grant_type")
        return JSONResponse(result)
    except OAuthError as exc:
        db.rollback()
        logger.info(
            "oauth_token_failed error=%s client_id=%s",
            exc.error,
            client_id[:64] if client_id else None,
        )
        return oauth_error_response(exc)


@router.post("/oauth/revoke", response_model=OAuthRevokeResponse)
def oauth_revoke(
    body: OAuthRevokeRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    user: CompanyUser = Depends(get_oauth_company_user),
):
    """Revoke one refresh-token family or all desktop sessions for this user+client.

    Rejects admin-impersonated company sessions.
    """
    check_oauth_rate_limit(scope="oauth_revoke_user", key=str(user.id), limit=30)
    try:
        if body.revoke_all:
            n = oauth_service.revoke_all_for_client_user(
                db, user_id=int(user.id), client_id=body.client_id
            )
            return OAuthRevokeResponse(ok=True, revoked=n)
        if not body.token:
            raise OAuthError(ERR_INVALID_REQUEST, description="token required unless revoke_all")
        n = oauth_service.revoke_refresh_token(
            db, token=body.token, client_id=body.client_id, user_id=int(user.id)
        )
        return OAuthRevokeResponse(ok=True, revoked=n)
    except OAuthError as exc:
        db.rollback()
        return oauth_error_response(exc)
