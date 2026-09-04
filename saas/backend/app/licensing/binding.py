"""License binding enforcement: 1 key = 1 website user + 1 device + 1 product.

Service-layer checks used by activation (Phase 7 APIs will call these).
No max_devices / shared-seat behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.licensing.constants import (
    ACTIVATION_STATUS_ACTIVE,
    ACTIVATION_STATUS_DEACTIVATED,
    ENTITLEMENT_PAID,
    ENTITLEMENT_TRIAL,
    LICENSE_STATUS_ACTIVE,
    LICENSE_STATUS_EXPIRED,
    LICENSE_STATUS_ISSUED,
    LICENSE_STATUS_REVOKED,
    LICENSE_STATUS_SUSPENDED,
)
from app.licensing.models import DesktopActivation, DesktopDevice, DesktopLicense, DesktopProduct


class LicenseBindingError(Exception):
    """Raised when an activation/bind attempt violates the 1:1:1 invariant."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class ActivationBindResult:
    license: DesktopLicense
    device: DesktopDevice
    activation: DesktopActivation
    created_new_activation: bool


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def assert_license_user_product(
    license_row: DesktopLicense,
    *,
    website_user_id: int,
    product_id: int,
) -> None:
    """Reject license used by another website user or another product."""
    if int(license_row.licensed_user_id) != int(website_user_id):
        raise LicenseBindingError(
            "wrong_user",
            "This license key is bound to a different website user and cannot be activated here.",
        )
    if int(license_row.product_id) != int(product_id):
        raise LicenseBindingError(
            "wrong_product",
            "This license key is for a different product and cannot be activated for this application.",
        )


def assert_license_not_expired_wall_clock(
    license_row: DesktopLicense, *, now: Optional[datetime] = None
) -> None:
    """Wall-clock expires_at always overrides stale issued/active status."""
    if license_row.expires_at is None:
        return
    when = now or _utc_now()
    exp = license_row.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp <= when:
        raise LicenseBindingError("expired", "This license has expired.")


def assert_license_paid_entitlement(license_row: DesktopLicense) -> None:
    """Legacy paid-only gate. Prefer assert_license_activatable_entitlement (Phase 7A)."""
    if (license_row.entitlement_type or "").lower() != ENTITLEMENT_PAID:
        raise LicenseBindingError(
            "trial_not_supported",
            "Trial entitlements are not supported for machine activation in this phase.",
        )


def assert_license_activatable_entitlement(license_row: DesktopLicense) -> None:
    """Phase 7A: machine API accepts paid and trial entitlements only."""
    ent = (license_row.entitlement_type or "").lower()
    if ent in (ENTITLEMENT_PAID, ENTITLEMENT_TRIAL):
        return
    raise LicenseBindingError(
        "unsupported_entitlement",
        f"Entitlement type '{license_row.entitlement_type}' cannot be activated.",
    )


def assert_license_not_terminal(license_row: DesktopLicense, *, now: Optional[datetime] = None) -> None:
    status = (license_row.status or "").strip().lower()
    if status == LICENSE_STATUS_REVOKED:
        raise LicenseBindingError("revoked", "This license has been revoked.")
    if status == LICENSE_STATUS_EXPIRED:
        raise LicenseBindingError("expired", "This license has expired.")
    if status == LICENSE_STATUS_SUSPENDED:
        raise LicenseBindingError("suspended", "This license is suspended.")
    if status not in (LICENSE_STATUS_ISSUED, LICENSE_STATUS_ACTIVE):
        raise LicenseBindingError("invalid_status", f"License status '{status}' cannot be activated.")
    assert_license_not_expired_wall_clock(license_row, now=now)


def get_active_activation(db: Session, license_id: int) -> Optional[DesktopActivation]:
    return db.execute(
        select(DesktopActivation).where(
            DesktopActivation.license_id == license_id,
            DesktopActivation.status == ACTIVATION_STATUS_ACTIVE,
        )
    ).scalar_one_or_none()


def get_activation_for_license_device(
    db: Session, *, license_id: int, device_id: int
) -> Optional[DesktopActivation]:
    """Return the unique (license_id, device_id) activation row if it exists (any status)."""
    return db.execute(
        select(DesktopActivation).where(
            DesktopActivation.license_id == int(license_id),
            DesktopActivation.device_id == int(device_id),
        )
    ).scalar_one_or_none()


def get_device_by_fingerprint(db: Session, *, fingerprint_hash: str) -> Optional[DesktopDevice]:
    """Lookup-only — does not create rows (validate/refresh must use this)."""
    fp = (fingerprint_hash or "").strip().lower()
    if not fp:
        return None
    return db.execute(
        select(DesktopDevice).where(DesktopDevice.fingerprint_hash == fp)
    ).scalar_one_or_none()


def get_or_create_device(
    db: Session,
    *,
    fingerprint_hash: str,
    fingerprint_raw_hint: Optional[str] = None,
    label: Optional[str] = None,
    os_meta: Optional[str] = None,
) -> DesktopDevice:
    fp = (fingerprint_hash or "").strip().lower()
    if not fp:
        raise LicenseBindingError("invalid_device", "Device fingerprint is required.")
    existing = db.execute(
        select(DesktopDevice).where(DesktopDevice.fingerprint_hash == fp)
    ).scalar_one_or_none()
    if existing:
        existing.last_seen_at = _utc_now()
        if label:
            existing.label = label
        if os_meta:
            existing.os_meta = os_meta
        return existing
    device = DesktopDevice(
        fingerprint_hash=fp,
        fingerprint_raw_hint=fingerprint_raw_hint,
        label=label,
        os_meta=os_meta,
        last_seen_at=_utc_now(),
    )
    db.add(device)
    db.flush()
    return device


def assert_device_binding_allowed(
    license_row: DesktopLicense,
    *,
    device: DesktopDevice,
    active_activation: Optional[DesktopActivation],
) -> None:
    """
    Enforce one physical system per license.

    - If bound_device_id is set to another device → reject.
    - If an active activation exists for another device → reject.
    - Same device re-activation / refresh → allowed.
    - No bound device and no active activation (e.g. after admin reset) → allowed.
    """
    if license_row.bound_device_id is not None and int(license_row.bound_device_id) != int(device.id):
        raise LicenseBindingError(
            "device_bound",
            "This license is already bound to another computer. "
            "Contact support for an admin-authorized device reset.",
        )
    if active_activation is not None and int(active_activation.device_id) != int(device.id):
        raise LicenseBindingError(
            "device_bound",
            "This license already has an active activation on another computer. "
            "Contact support for an admin-authorized device reset.",
        )


def activate_license_on_device(
    db: Session,
    *,
    license_row: DesktopLicense,
    website_user_id: int,
    product_id: int,
    fingerprint_hash: str,
    fingerprint_raw_hint: Optional[str] = None,
    label: Optional[str] = None,
    os_meta: Optional[str] = None,
    app_version: Optional[str] = None,
) -> ActivationBindResult:
    """
    Bind (first activation), reaffirm (same active device), or reactivate
    a previously deactivated (license_id, device_id) row.

    Locks the license row for concurrent first-bind protection when supported.
    Caller must commit the transaction.

    UNIQUE(license_id, device_id) is preserved: never INSERT a duplicate pair.
    """
    # Concurrent first-bind protection
    locked = db.execute(
        select(DesktopLicense).where(DesktopLicense.id == license_row.id).with_for_update()
    ).scalar_one()

    assert_license_not_terminal(locked)
    assert_license_activatable_entitlement(locked)
    assert_license_user_product(locked, website_user_id=website_user_id, product_id=product_id)

    # Optional: confirm product row exists / matches code path callers already have product_id
    product = db.get(DesktopProduct, product_id)
    if product is None or int(product.id) != int(locked.product_id):
        raise LicenseBindingError(
            "wrong_product",
            "This license key is for a different product and cannot be activated for this application.",
        )

    device = get_or_create_device(
        db,
        fingerprint_hash=fingerprint_hash,
        fingerprint_raw_hint=fingerprint_raw_hint,
        label=label,
        os_meta=os_meta,
    )

    active = get_active_activation(db, locked.id)
    assert_device_binding_allowed(locked, device=device, active_activation=active)

    # Same device already active → reaffirm
    if active is not None and int(active.device_id) == int(device.id):
        active.last_validated_at = _utc_now()
        if app_version:
            active.app_version = app_version
        locked.bound_device_id = device.id
        if locked.status == LICENSE_STATUS_ISSUED:
            locked.status = LICENSE_STATUS_ACTIVE
            locked.activated_at = locked.activated_at or _utc_now()
        return ActivationBindResult(
            license=locked,
            device=device,
            activation=active,
            created_new_activation=False,
        )

    # Existing row for this (license, device) — reactivate instead of INSERT
    existing = get_activation_for_license_device(db, license_id=locked.id, device_id=device.id)
    if existing is not None:
        if (existing.status or "").lower() == ACTIVATION_STATUS_ACTIVE:
            # Defensive: should have been handled above via get_active_activation
            existing.last_validated_at = _utc_now()
            if app_version:
                existing.app_version = app_version
            locked.bound_device_id = device.id
            if locked.status == LICENSE_STATUS_ISSUED:
                locked.status = LICENSE_STATUS_ACTIVE
                locked.activated_at = locked.activated_at or _utc_now()
            return ActivationBindResult(
                license=locked,
                device=device,
                activation=existing,
                created_new_activation=False,
            )
        # Deactivated (or other non-active) → reactivate SAME row; preserve id/history
        now = _utc_now()
        existing.status = ACTIVATION_STATUS_ACTIVE
        existing.deactivated_at = None
        existing.user_id = website_user_id
        existing.last_validated_at = now
        # Keep original activated_at for history; do not wipe identity
        if app_version:
            existing.app_version = app_version
        locked.bound_device_id = device.id
        locked.status = LICENSE_STATUS_ACTIVE
        if locked.activated_at is None:
            locked.activated_at = now
        db.add(existing)
        db.flush()
        return ActivationBindResult(
            license=locked,
            device=device,
            activation=existing,
            created_new_activation=False,
        )

    # No prior (license, device) row — first bind for this pair
    activation = DesktopActivation(
        license_id=locked.id,
        user_id=website_user_id,
        device_id=device.id,
        status=ACTIVATION_STATUS_ACTIVE,
        activated_at=_utc_now(),
        last_validated_at=_utc_now(),
        app_version=app_version,
    )
    db.add(activation)
    locked.bound_device_id = device.id
    locked.status = LICENSE_STATUS_ACTIVE
    if locked.activated_at is None:
        locked.activated_at = _utc_now()
    db.flush()
    return ActivationBindResult(
        license=locked,
        device=device,
        activation=activation,
        created_new_activation=True,
    )


@dataclass(frozen=True)
class AdminResetResult:
    license: DesktopLicense
    previous_activation_id: Optional[int]
    previous_device_id: Optional[int]


def admin_reset_device_binding(
    db: Session,
    *,
    license_row: DesktopLicense,
    admin_id: int,
) -> AdminResetResult:
    """
    Admin-authorized machine replacement: clear device bind and deactivate active activation.
    Does NOT reassign the license to another website user or product.
    Does NOT auto-activate a replacement device.
    """
    locked = db.execute(
        select(DesktopLicense).where(DesktopLicense.id == license_row.id).with_for_update()
    ).scalar_one()
    active = get_active_activation(db, locked.id)
    prev_act = int(active.id) if active and active.id is not None else None
    prev_dev = int(active.device_id) if active else (
        int(locked.bound_device_id) if locked.bound_device_id is not None else None
    )
    if active:
        active.status = ACTIVATION_STATUS_DEACTIVATED
        active.deactivated_at = _utc_now()
    locked.bound_device_id = None
    if locked.status == LICENSE_STATUS_ACTIVE:
        locked.status = LICENSE_STATUS_ISSUED
    _ = admin_id
    db.flush()
    return AdminResetResult(
        license=locked,
        previous_activation_id=prev_act,
        previous_device_id=prev_dev,
    )


def deactivate_activation_preserve_binding(
    db: Session,
    *,
    license_row: DesktopLicense,
    website_user_id: int,
    product_id: int,
    fingerprint_hash: str,
) -> DesktopActivation:
    """
    Client deactivate: mark active activation deactivated but KEEP bound_device_id.
    Other devices remain denied until admin reset.
    """
    locked = db.execute(
        select(DesktopLicense).where(DesktopLicense.id == license_row.id).with_for_update()
    ).scalar_one()
    assert_license_user_product(locked, website_user_id=website_user_id, product_id=product_id)
    device = db.execute(
        select(DesktopDevice).where(DesktopDevice.fingerprint_hash == (fingerprint_hash or "").strip().lower())
    ).scalar_one_or_none()
    if device is None:
        raise LicenseBindingError("invalid_device", "Device fingerprint is required.")
    if locked.bound_device_id is not None and int(locked.bound_device_id) != int(device.id):
        raise LicenseBindingError(
            "device_bound",
            "This license is bound to another computer.",
        )
    active = get_active_activation(db, locked.id)
    if active is None:
        raise LicenseBindingError("invalid_status", "No active activation to deactivate.")
    if int(active.device_id) != int(device.id):
        raise LicenseBindingError(
            "device_bound",
            "This license is bound to another computer.",
        )
    active.status = ACTIVATION_STATUS_DEACTIVATED
    active.deactivated_at = _utc_now()
    # bound_device_id intentionally preserved
    device.last_seen_at = _utc_now()
    db.flush()
    return active
