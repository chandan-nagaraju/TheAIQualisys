"""Constants for desktop OAuth (Phase 9C-B)."""

from __future__ import annotations

SCOPE_DESKTOP_LICENSE = "desktop_license"
SUPPORTED_SCOPES = frozenset({SCOPE_DESKTOP_LICENSE})

CLIENT_TYPE_PUBLIC = "public"
CODE_CHALLENGE_METHOD_S256 = "S256"
RESPONSE_TYPE_CODE = "code"

GRANT_AUTHORIZATION_CODE = "authorization_code"
GRANT_REFRESH_TOKEN = "refresh_token"
TOKEN_TYPE_BEARER = "Bearer"

DESKTOP_JWT_AUD = "aiqualisys-desktop"
DESKTOP_JWT_ISS = "aiqualisys"

DEFAULT_ACCESS_TOKEN_MINUTES = 30
DEFAULT_REFRESH_TOKEN_DAYS = 90
DEFAULT_AUTH_CODE_TTL_SECONDS = 180

REVOKE_SIGN_OUT = "sign_out"
REVOKE_SIGN_OUT_ALL = "sign_out_all"
REVOKE_USER_BLOCKED = "user_blocked"
REVOKE_PASSWORD_CHANGED = "password_changed"
REVOKE_MEMBERSHIP_CHANGED = "membership_changed"
REVOKE_REFRESH_REPLAY = "refresh_replay"
REVOKE_ADMIN = "admin_revoke"
REVOKE_CLIENT_DISABLED = "client_disabled"
REVOKE_REPLACED = "rotated"

AUDIT_AUTHORIZATION_STARTED = "desktop_authorization_started"
AUDIT_AUTHORIZATION_GRANTED = "desktop_authorization_granted"
AUDIT_AUTHORIZATION_DENIED = "desktop_authorization_denied"
AUDIT_TOKEN_ISSUED = "desktop_token_issued"
AUDIT_TOKEN_REFRESHED = "desktop_token_refreshed"
AUDIT_REFRESH_REPLAY = "desktop_refresh_replay_detected"
AUDIT_SESSION_REVOKED = "desktop_session_revoked"

ERR_INVALID_REQUEST = "invalid_request"
ERR_INVALID_CLIENT = "invalid_client"
ERR_INVALID_GRANT = "invalid_grant"
ERR_INVALID_SCOPE = "invalid_scope"
ERR_UNAUTHORIZED_CLIENT = "unauthorized_client"
ERR_ACCESS_DENIED = "access_denied"
ERR_UNSUPPORTED_GRANT = "unsupported_grant_type"
ERR_UNSUPPORTED_RESPONSE = "unsupported_response_type"
ERR_SERVER_ERROR = "server_error"

SENSITIVE_META_KEYS = frozenset({
    "access_token", "refresh_token", "code", "authorization_code",
    "code_verifier", "code_challenge", "password", "token", "jwt",
    "id_token", "authorization", "bearer",
})
