"""Phase 7 machine-license service: activate / validate / refresh / deactivate."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.licensing.binding import (
    LicenseBindingError,
    activate_license_on_device,
    deactivate_activation_preserve_binding,
    get_active_activation,
)
from app.licensing.constants import (
    ENTITLEMENT_PAID,
    LICENSE_MAX_OFFLINE_DAYS_DEFAULT,
    LICENSE_STATUS_ACTIVE,
    LICENSE_STATUS_EXPIRED,
    LICENSE_STATUS_ISSUED,
    MACHINE_ERR_DEVICE_BOUND,
    MACHINE_ERR_EXPIRED,
    MACHINE_ERR_INVALID_DEVICE,
    MACHINE_ERR_INVALID_LICENSE,
    MACHINE_ERR_INVALID_REQUEST,
    MACHINE_ERR_INVALID_STATUS,
    MACHINE_ERR_REVOKED,
    MACHINE_ERR_SIGNING_UNAVAILABLE,
    MACHINE_ERR_SUSPENDED,
    MACHINE_ERR_TRIAL_NOT_SUPPORTED,
    MACHINE_ERR_WRONG_PRODUCT,
    MACHINE_ERR_WRONG_USER,
)
from app.licensing.keys import hash_license_key
from app.licensing.models import DesktopLicense, DesktopProduct
from app.licensing.service import record_license_event
from app.licensing.signing import (
    SigningKeyError,
    build_entitlement_claims,
    sign_entitlement,
    validate_fingerprint_hash,
)
from app.models import CompanyUser


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def machine_http_error(code: str, message: str, *, http_status: int) -> HTTPException:
    return HTTPException(status_code=http_status, detail={"code": code, "message": message})


def map_binding_error(exc: LicenseBindingError) -> HTTPException:
    code = exc.code
    if code == "wrong_user":
        return machine_http_error(MACHINE_ERR_WRONG_USER, str(exc), http_status=403)
    if code == "wrong_product":
        return machine_http_error(MACHINE_ERR_WRONG_PRODUCT, str(exc), http_status=403)
    if code == "expired":
        return machine_http_error(MACHINE_ERR_EXPIRED, str(exc), http_status=403)
    if code == "revoked":
        return machine_http_error(MACHINE_ERR_REVOKED, str(exc), http_status=403)
    if code == "suspended":
        return machine_http_error(MACHINE_ERR_SUSPENDED, str(exc), http_status=403)
    if code == "device_bound":
        return machine_http_error(MACHINE_ERR_DEVICE_BOUND, str(exc), http_status=409)
    if code == "invalid_device":
        return machine_http_error(MACHINE_ERR_INVALID_DEVICE, str(exc), http_status=400)
    if code == "trial_not_supported":
        return machine_http_error(MACHINE_ERR_TRIAL_NOT_SUPPORTED, str(exc), http_status=403)
    if code == "invalid_status":
        return machine_http_error(MACHINE_ERR_INVALID_STATUS, str(exc), http_status=403)
    return machine_http_error(MACHINE_ERR_INVALID_REQUEST, str(exc), http_status=400)


def _maybe_mark_expired(license_row: DesktopLicense, *, now: Optional[datetime] = None) -> None:
    when = now or _utc_now()
    if license_row.expires_at is None:
        return
    exp = license_row.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp <= when and (license_row.status or "").lower() in (
        LICENSE_STATUS_ISSUED,
        LICENSE_STATUS_ACTIVE,
    ):
        license_row.status = LICENSE_STATUS_EXPIRED


def _product_by_code(db: Session, product_code: str) -> DesktopProduct:
    code = (product_code or "").strip().upper()
    if not code:
        raise machine_http_error(
            MACHINE_ERR_INVALID_REQUEST, "product_code is required", http_status=400
        )
    product = db.execute(select(DesktopProduct).where(DesktopProduct.code == code)).scalar_one_or_none()
    if not product or not bool(product.listing_active):
        raise machine_http_error(MACHINE_ERR_WRONG_PRODUCT, "Unknown or inactive product", http_status=403)
    return product


def _lookup_license_by_key(db: Session, license_key: str) -> DesktopLicense:
    key = (license_key or "").strip()
    if not key:
        raise machine_http_error(
            MACHINE_ERR_INVALID_LICENSE, "License key is required", http_status=400
        )
    digest = hash_license_key(key)
    row = db.execute(select(DesktopLicense).where(DesktopLicense.key_hash == digest)).scalar_one_or_none()
    if not row:
        raise machine_http_error(
            MACHINE_ERR_INVALID_LICENSE, "Invalid license key", http_status=404
        )
    return row


def _get_owned_license(db: Session, *, user: CompanyUser, license_id: int) -> DesktopLicense:
    row = db.get(DesktopLicense, int(license_id))
    if not row:
        raise machine_http_error(MACHINE_ERR_INVALID_LICENSE, "License not found", http_status=404)
    if int(row.licensed_user_id) != int(user.id):
        raise machine_http_error(
            MACHINE_ERR_WRONG_USER,
            "This license key is bound to a different website user.",
            http_status=403,
        )
    return row


def _max_offline_days(settings: Settings) -> int:
    return int(getattr(settings, "license_max_offline_days", None) or LICENSE_MAX_OFFLINE_DAYS_DEFAULT)


def _issue_token(
    settings: Settings,
    *,
    license_row: DesktopLicense,
    product: DesktopProduct,
    activation_id: int,
    fingerprint_hash: str,
) -> tuple[str, dict[str, Any]]:
    try:
        claims = build_entitlement_claims(
            product_code=product.code,
            license_id=int(license_row.id),
            activation_id=int(activation_id),
            licensed_user_id=int(license_row.licensed_user_id),
            fingerprint_hash=fingerprint_hash,
            entitlement_type=(license_row.entitlement_type or ENTITLEMENT_PAID),
            status="active",
            expires_at=license_row.expires_at,
            max_offline_days=_max_offline_days(settings),
        )
        token = sign_entitlement(settings, claims)
    except SigningKeyError as exc:
        raise machine_http_error(
            MACHINE_ERR_SIGNING_UNAVAILABLE,
            "License signing is unavailable",
            http_status=503,
        ) from exc
    return token, claims


def _integrity_constraint_name(exc: IntegrityError) -> str:
    orig = getattr(exc, "orig", None)
    diag = getattr(orig, "diag", None) if orig is not None else None
    name = getattr(diag, "constraint_name", None) if diag is not None else None
    if name:
        return str(name).lower()
    return ""


def _integrity_error_text(exc: IntegrityError) -> str:
    parts = [
        _integrity_constraint_name(exc),
        str(getattr(exc, "orig", "") or ""),
        str(exc),
    ]
    return " ".join(parts).lower()


def is_one_active_activation_conflict(exc: IntegrityError) -> bool:
    """
    True only for the partial unique index that enforces one active activation per license.
    Must NOT match UNIQUE(license_id, device_id) or fingerprint_hash uniqueness.
    """
    name = _integrity_constraint_name(exc)
    if name == "uq_desktop_activations_one_active_per_license":
        return True
    text = _integrity_error_text(exc)
    if "uq_desktop_activations_one_active_per_license" in text:
        return True
    return False


def is_license_device_pair_conflict(exc: IntegrityError) -> bool:
    """UNIQUE(license_id, device_id) — should be rare after reactivation path; not device_bound."""
    name = _integrity_constraint_name(exc)
    if name in {"uq_desktop_activations_license_device", "desktop_activations_license_id_device_id_key"}:
        return True
    text = _integrity_error_text(exc)
    if "uq_desktop_activations_license_device" in text:
        return True
    # Avoid matching the one-active index
    if "one_active" in text:
        return False
    if "license_id" in text and "device_id" in text and ("unique" in text or "duplicate" in text):
        return True
    return False


def activate_machine_license(
    db: Session,
    settings: Settings,
    *,
    user: CompanyUser,
    license_key: str,
    product_code: str,
    fingerprint_hash: str,
    device_label: Optional[str] = None,
    os_meta: Optional[str] = None,
    app_version: Optional[str] = None,
) -> dict[str, Any]:
    try:
        fp = validate_fingerprint_hash(fingerprint_hash)
    except ValueError as exc:
        raise machine_http_error(MACHINE_ERR_INVALID_DEVICE, str(exc), http_status=400) from exc

    product = _product_by_code(db, product_code)
    license_row = _lookup_license_by_key(db, license_key)
    _maybe_mark_expired(license_row)

    try:
        result = activate_license_on_device(
            db,
            license_row=license_row,
            website_user_id=int(user.id),
            product_id=int(product.id),
            fingerprint_hash=fp,
            fingerprint_raw_hint=None,
            label=(device_label or "").strip() or None,
            os_meta=(os_meta or "").strip() or None,
            app_version=(app_version or "").strip() or None,
        )
    except LicenseBindingError as exc:
        raise map_binding_error(exc) from exc
    except IntegrityError as exc:
        # Roll back the failed flush unit so the session can continue cleanly.
        db.rollback()
        if is_one_active_activation_conflict(exc):
            raise machine_http_error(
                MACHINE_ERR_DEVICE_BOUND,
                "This license is already bound to another computer. "
                "Contact support for an admin-authorized device reset.",
                http_status=409,
            ) from exc
        if is_license_device_pair_conflict(exc):
            raise machine_http_error(
                MACHINE_ERR_INVALID_REQUEST,
                "Activation state conflict for this device. Retry activation.",
                http_status=409,
            ) from exc
        raise machine_http_error(
            MACHINE_ERR_INVALID_REQUEST,
            "Could not complete activation due to a data integrity conflict.",
            http_status=409,
        ) from exc

    token, claims = _issue_token(
        settings,
        license_row=result.license,
        product=product,
        activation_id=int(result.activation.id),
        fingerprint_hash=fp,
    )
    event = "license_activated" if result.created_new_activation else "license_reaffirmed"
    record_license_event(
        db,
        license_id=result.license.id,
        actor_type="user",
        actor_id=user.id,
        event_type=event,
        meta={
            "activation_id": result.activation.id,
            "device_id": result.device.id,
            "product_code": product.code,
            "jti": claims.get("jti"),
            # never log license_key, token, or secrets
        },
    )
    return {
        "license_id": result.license.id,
        "activation_id": result.activation.id,
        "product_code": product.code,
        "status": result.license.status,
        "expires_at": result.license.expires_at.isoformat() if result.license.expires_at else None,
        "device_bound": True,
        "reaffirmed": not result.created_new_activation,
        "entitlement_token": token,
        "token_naf": claims.get("naf"),
        "token_jti": claims.get("jti"),
    }


def _require_bound_active(
    db: Session,
    *,
    user: CompanyUser,
    license_id: int,
    product_code: str,
    fingerprint_hash: str,
    app_version: Optional[str] = None,
) -> tuple[DesktopLicense, DesktopProduct, Any]:
    try:
        fp = validate_fingerprint_hash(fingerprint_hash)
    except ValueError as exc:
        raise machine_http_error(MACHINE_ERR_INVALID_DEVICE, str(exc), http_status=400) from exc

    product = _product_by_code(db, product_code)
    license_row = _get_owned_license(db, user=user, license_id=license_id)
    if int(license_row.product_id) != int(product.id):
        raise machine_http_error(
            MACHINE_ERR_WRONG_PRODUCT,
            "This license key is for a different product.",
            http_status=403,
        )
    _maybe_mark_expired(license_row)

    from app.licensing.binding import (
        assert_license_not_terminal,
        assert_license_paid_entitlement,
        get_device_by_fingerprint,
        assert_device_binding_allowed,
    )

    locked = db.execute(
        select(DesktopLicense).where(DesktopLicense.id == license_row.id).with_for_update()
    ).scalar_one()
    try:
        assert_license_paid_entitlement(locked)
        assert_license_not_terminal(locked)
        device = get_device_by_fingerprint(db, fingerprint_hash=fp)
        if device is None:
            raise LicenseBindingError(
                "device_bound",
                "This license is already bound to another computer.",
            )
        active = get_active_activation(db, locked.id)
        if active is None:
            raise LicenseBindingError("invalid_status", "License has no active activation.")
        assert_device_binding_allowed(locked, device=device, active_activation=active)
        if int(active.device_id) != int(device.id):
            raise LicenseBindingError(
                "device_bound",
                "This license is already bound to another computer.",
            )
        if locked.bound_device_id is None or int(locked.bound_device_id) != int(device.id):
            raise LicenseBindingError(
                "device_bound",
                "This license is already bound to another computer.",
            )
    except LicenseBindingError as exc:
        raise map_binding_error(exc) from exc

    active.last_validated_at = _utc_now()
    if app_version:
        active.app_version = app_version.strip() or active.app_version
    device.last_seen_at = _utc_now()
    db.flush()
    return locked, product, active


def validate_machine_license(
    db: Session,
    settings: Settings,
    *,
    user: CompanyUser,
    license_id: int,
    product_code: str,
    fingerprint_hash: str,
    app_version: Optional[str] = None,
) -> dict[str, Any]:
    locked, product, active = _require_bound_active(
        db,
        user=user,
        license_id=license_id,
        product_code=product_code,
        fingerprint_hash=fingerprint_hash,
        app_version=app_version,
    )
    fp = validate_fingerprint_hash(fingerprint_hash)
    token, claims = _issue_token(
        settings,
        license_row=locked,
        product=product,
        activation_id=int(active.id),
        fingerprint_hash=fp,
    )
    record_license_event(
        db,
        license_id=locked.id,
        actor_type="user",
        actor_id=user.id,
        event_type="license_validated",
        meta={"activation_id": active.id, "device_id": active.device_id, "jti": claims.get("jti")},
    )
    return {
        "license_id": locked.id,
        "activation_id": active.id,
        "product_code": product.code,
        "status": locked.status,
        "expires_at": locked.expires_at.isoformat() if locked.expires_at else None,
        "device_bound": True,
        "entitlement_token": token,
        "token_naf": claims.get("naf"),
        "token_jti": claims.get("jti"),
    }


def refresh_machine_license(
    db: Session,
    settings: Settings,
    *,
    user: CompanyUser,
    license_id: int,
    product_code: str,
    fingerprint_hash: str,
    app_version: Optional[str] = None,
) -> dict[str, Any]:
    locked, product, active = _require_bound_active(
        db,
        user=user,
        license_id=license_id,
        product_code=product_code,
        fingerprint_hash=fingerprint_hash,
        app_version=app_version,
    )
    fp = validate_fingerprint_hash(fingerprint_hash)
    token, claims = _issue_token(
        settings,
        license_row=locked,
        product=product,
        activation_id=int(active.id),
        fingerprint_hash=fp,
    )
    record_license_event(
        db,
        license_id=locked.id,
        actor_type="user",
        actor_id=user.id,
        event_type="license_refreshed",
        meta={"activation_id": active.id, "device_id": active.device_id, "jti": claims.get("jti")},
    )
    return {
        "license_id": locked.id,
        "activation_id": active.id,
        "product_code": product.code,
        "status": locked.status,
        "expires_at": locked.expires_at.isoformat() if locked.expires_at else None,
        "device_bound": True,
        "entitlement_token": token,
        "token_naf": claims.get("naf"),
        "token_jti": claims.get("jti"),
    }


def deactivate_machine_license(
    db: Session,
    *,
    user: CompanyUser,
    license_id: int,
    product_code: str,
    fingerprint_hash: str,
) -> dict[str, Any]:
    try:
        fp = validate_fingerprint_hash(fingerprint_hash)
    except ValueError as exc:
        raise machine_http_error(MACHINE_ERR_INVALID_DEVICE, str(exc), http_status=400) from exc
    product = _product_by_code(db, product_code)
    license_row = _get_owned_license(db, user=user, license_id=license_id)
    if int(license_row.product_id) != int(product.id):
        raise machine_http_error(
            MACHINE_ERR_WRONG_PRODUCT,
            "This license key is for a different product.",
            http_status=403,
        )
    try:
        active = deactivate_activation_preserve_binding(
            db,
            license_row=license_row,
            website_user_id=int(user.id),
            product_id=int(product.id),
            fingerprint_hash=fp,
        )
    except LicenseBindingError as exc:
        raise map_binding_error(exc) from exc

    # Reload to confirm binding preserved
    locked = db.get(DesktopLicense, int(license_row.id))
    record_license_event(
        db,
        license_id=license_row.id,
        actor_type="user",
        actor_id=user.id,
        event_type="license_deactivated_client",
        meta={
            "activation_id": active.id,
            "device_id": active.device_id,
            "binding_preserved": True,
            "bound_device_id": locked.bound_device_id if locked else None,
        },
    )
    return {
        "deactivated": True,
        "binding_preserved": True,
        "license_id": license_row.id,
        "bound_device_id": locked.bound_device_id if locked else None,
    }
