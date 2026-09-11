"""Audit helpers — never log tokens, codes, or PKCE secrets."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.oauth.constants import SENSITIVE_META_KEYS as SENSITIVE_META_KEYS
from app.oauth.models import OAuthDesktopAuditEvent


def _sanitize_meta(meta: dict[str, Any] | None) -> dict[str, Any] | None:
    if not meta:
        return None
    out: dict[str, Any] = {}
    for k, v in meta.items():
        key = str(k).lower()
        if key in SENSITIVE_META_KEYS or any(
            s in key for s in ("token", "secret", "password", "verifier", "jwt", "code")
        ):
            continue
        if isinstance(v, str) and len(v) > 500:
            out[k] = v[:500] + "…"
        else:
            out[k] = v
    return out or None


def record_oauth_audit(
    db: Session,
    *,
    event_type: str,
    success: bool,
    user_id: int | None = None,
    company_id: int | None = None,
    client_id: str | None = None,
    error_code: str | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    db.add(
        OAuthDesktopAuditEvent(
            event_type=event_type,
            success=1 if success else 0,
            user_id=user_id,
            company_id=company_id,
            client_id=client_id,
            error_code=error_code,
            meta=_sanitize_meta(meta),
        )
    )
