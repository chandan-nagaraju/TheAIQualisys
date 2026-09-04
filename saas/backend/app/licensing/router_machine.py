"""Machine license API — Phase 7 (Ed25519 entitlements + device binding).

Paths:
  POST /api/license/activate
  POST /api/license/validate
  POST /api/license/refresh
  POST /api/license/deactivate
  GET  /api/license/public-key

Desktop apps must pin the production public key in the signed release.
GET /api/license/public-key is informational / rotation assist — not the trust root.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.deps import get_current_company_user, get_db_session
from app.licensing.feature_flag import require_desktop_licensing_enabled
from app.licensing.machine import (
    activate_machine_license,
    deactivate_machine_license,
    refresh_machine_license,
    validate_machine_license,
)
from app.licensing.rate_limit import check_rate_limit, default_machine_limit
from app.licensing.schemas import (
    LicenseActivateIn,
    LicenseDeactivateIn,
    LicenseDeactivateOut,
    LicenseMachineEntitlementOut,
    LicensePublicKeyOut,
    LicenseRefreshIn,
    LicenseValidateIn,
)
from app.licensing.signing import SigningKeyError, public_key_response
from app.licensing.machine import machine_http_error
from app.licensing.constants import MACHINE_ERR_SIGNING_UNAVAILABLE
from app.models import CompanyUser

router = APIRouter(prefix="/api/license", tags=["license-machine"])


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for") or ""
    if forwarded:
        return forwarded.split(",")[0].strip() or "unknown"
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


@router.post("/activate", response_model=LicenseMachineEntitlementOut)
def license_activate(
    body: LicenseActivateIn,
    request: Request,
    _: None = Depends(require_desktop_licensing_enabled),
    user: CompanyUser = Depends(get_current_company_user),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    ip = _client_ip(request)
    base = int(settings.license_api_rate_limit_per_minute or default_machine_limit())
    check_rate_limit(scope="license_activate_ip", key=ip, limit=min(10, base))
    check_rate_limit(scope="license_activate_user", key=str(user.id), limit=min(10, base))
    # Count attempts even for unknown keys (hash of presented key material length-safe)
    from app.licensing.keys import hash_license_key

    key_bucket = hash_license_key(body.license_key or "empty")[:16]
    check_rate_limit(scope="license_activate_key", key=key_bucket, limit=5)

    try:
        out = activate_machine_license(
            db,
            settings,
            user=user,
            license_key=body.license_key,
            product_code=body.product_code,
            fingerprint_hash=body.fingerprint_hash,
            device_label=body.device_label,
            os_meta=body.os_meta,
            app_version=body.app_version,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return out


@router.post("/validate", response_model=LicenseMachineEntitlementOut)
def license_validate(
    body: LicenseValidateIn,
    request: Request,
    _: None = Depends(require_desktop_licensing_enabled),
    user: CompanyUser = Depends(get_current_company_user),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    del request
    base = int(settings.license_api_rate_limit_per_minute or default_machine_limit())
    check_rate_limit(
        scope="license_validate",
        key=f"{user.id}:{body.license_id}",
        limit=base,
    )
    try:
        out = validate_machine_license(
            db,
            settings,
            user=user,
            license_id=body.license_id,
            product_code=body.product_code,
            fingerprint_hash=body.fingerprint_hash,
            app_version=body.app_version,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return out


@router.post("/refresh", response_model=LicenseMachineEntitlementOut)
def license_refresh(
    body: LicenseRefreshIn,
    request: Request,
    _: None = Depends(require_desktop_licensing_enabled),
    user: CompanyUser = Depends(get_current_company_user),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    del request
    base = int(settings.license_api_rate_limit_per_minute or default_machine_limit())
    check_rate_limit(
        scope="license_refresh",
        key=f"{user.id}:{body.license_id}",
        limit=base,
    )
    try:
        out = refresh_machine_license(
            db,
            settings,
            user=user,
            license_id=body.license_id,
            product_code=body.product_code,
            fingerprint_hash=body.fingerprint_hash,
            app_version=body.app_version,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return out


@router.post("/deactivate", response_model=LicenseDeactivateOut)
def license_deactivate(
    body: LicenseDeactivateIn,
    request: Request,
    _: None = Depends(require_desktop_licensing_enabled),
    user: CompanyUser = Depends(get_current_company_user),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    del request
    base = int(settings.license_api_rate_limit_per_minute or default_machine_limit())
    check_rate_limit(scope="license_deactivate", key=str(user.id), limit=min(10, base))
    try:
        out = deactivate_machine_license(
            db,
            user=user,
            license_id=body.license_id,
            product_code=body.product_code,
            fingerprint_hash=body.fingerprint_hash,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return out


@router.get("/public-key", response_model=LicensePublicKeyOut)
def license_public_key(
    request: Request,
    _: None = Depends(require_desktop_licensing_enabled),
    settings: Settings = Depends(get_settings),
):
    ip = _client_ip(request)
    check_rate_limit(scope="license_public_key", key=ip, limit=60)
    try:
        return public_key_response(settings)
    except SigningKeyError as exc:
        raise machine_http_error(
            MACHINE_ERR_SIGNING_UNAVAILABLE,
            "License signing is unavailable",
            http_status=503,
        ) from exc
