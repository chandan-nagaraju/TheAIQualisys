"""Phase 5: My Licenses list/reveal + post-mint license email (no remint on email retry)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import Settings
from app.email_util import is_email_configured, send_plain_text_email
from app.licensing.constants import (
    LICENSE_EMAIL_FAILED,
    LICENSE_EMAIL_PENDING,
    LICENSE_EMAIL_RESEND_MAX_ATTEMPTS_PER_HOUR,
    LICENSE_EMAIL_RESEND_MIN_SECONDS,
    LICENSE_EMAIL_SENT,
    LICENSE_STATUS_ACTIVE,
    LICENSE_STATUS_ISSUED,
)
from app.licensing.keys import LicenseKeyEncryptionError, decrypt_license_key
from app.licensing.models import (
    DesktopLicense,
    DesktopLicenseEmailDelivery,
    DesktopOrder,
    DesktopPlan,
    DesktopProduct,
)
from app.licensing.service import record_license_event
from app.models import CompanyUser, PlatformAdmin


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def masked_key_from_parts(prefix: str, last4: str) -> str:
    """Masked display without decrypting ciphertext."""
    p = (prefix or "AQ").strip() or "AQ"
    l4 = (last4 or "****").strip() or "****"
    return f"{p}-••••••••••••{l4}"


def device_activation_label(lic: DesktopLicense) -> str:
    """Human-readable activation state from Phase 1/4 data only (no fake activation)."""
    if lic.bound_device_id is not None or lic.activated_at is not None:
        return "Activated"
    if (lic.status or "").lower() == LICENSE_STATUS_ACTIVE:
        return "Active"
    if (lic.status or "").lower() == LICENSE_STATUS_ISSUED:
        return "Not activated"
    return (lic.status or "unknown").replace("_", " ").title()


def serialize_license_public(
    lic: DesktopLicense,
    *,
    order: Optional[DesktopOrder] = None,
    product: Optional[DesktopProduct] = None,
    plan: Optional[DesktopPlan] = None,
    email_delivery: Optional[DesktopLicenseEmailDelivery] = None,
) -> dict[str, Any]:
    """Customer/admin safe license payload — never includes plaintext or ciphertext."""
    ord_row = order or getattr(lic, "order", None)
    prod = product
    pln = plan
    out: dict[str, Any] = {
        "id": lic.id,
        "product_id": lic.product_id,
        "plan_id": lic.plan_id,
        "order_id": lic.order_id,
        "company_id": lic.company_id,
        "licensed_user_id": lic.licensed_user_id,
        "entitlement_type": lic.entitlement_type,
        "seat_index": lic.seat_index,
        "status": lic.status,
        "key_masked": masked_key_from_parts(lic.key_prefix, lic.key_last4),
        "key_prefix": lic.key_prefix,
        "key_last4": lic.key_last4,
        "issued_at": lic.issued_at.isoformat() if lic.issued_at else None,
        "expires_at": lic.expires_at.isoformat() if lic.expires_at else None,
        "activated_at": lic.activated_at.isoformat() if lic.activated_at else None,
        "bound_device_id": lic.bound_device_id,
        "device_status": device_activation_label(lic),
        "is_activated": bool(lic.bound_device_id is not None or lic.activated_at is not None),
    }
    if ord_row is not None:
        out["order_number"] = ord_row.order_number
        out["product_code"] = ord_row.product_code
        out["product_name"] = ord_row.product_name
        out["plan_code"] = ord_row.plan_code
        out["plan_name"] = ord_row.plan_name
        out["duration_days"] = ord_row.duration_days
        out["order_seats"] = ord_row.seats
    elif prod is not None:
        out["product_code"] = prod.code
        out["product_name"] = prod.name
    if pln is not None and "plan_name" not in out:
        out["plan_code"] = pln.code
        out["plan_name"] = pln.name
        out["duration_days"] = pln.duration_days
    if email_delivery is not None:
        out["email_status"] = email_delivery.status
        out["email_sent_at"] = email_delivery.sent_at.isoformat() if email_delivery.sent_at else None
    return out


def serialize_email_delivery(row: DesktopLicenseEmailDelivery) -> dict[str, Any]:
    return {
        "id": row.id,
        "order_id": row.order_id,
        "status": row.status,
        "attempt_count": row.attempt_count,
        "last_attempted_at": row.last_attempted_at.isoformat() if row.last_attempted_at else None,
        "sent_at": row.sent_at.isoformat() if row.sent_at else None,
        "last_error": row.last_error,
        "to_email": row.to_email,
    }


def list_licenses_for_user(db: Session, *, user: CompanyUser, limit: int = 200) -> list[DesktopLicense]:
    lim = max(1, min(int(limit), 500))
    return list(
        db.execute(
            select(DesktopLicense)
            .options(selectinload(DesktopLicense.order))  # type: ignore[attr-defined]
            .where(DesktopLicense.licensed_user_id == int(user.id))
            .order_by(DesktopLicense.id.desc())
            .limit(lim)
        ).scalars().all()
    )


def get_owned_license(db: Session, *, user: CompanyUser, license_id: int) -> DesktopLicense:
    lic = db.execute(
        select(DesktopLicense)
        .options(selectinload(DesktopLicense.order))  # type: ignore[attr-defined]
        .where(DesktopLicense.id == int(license_id))
    ).scalar_one_or_none()
    if not lic or int(lic.licensed_user_id) != int(user.id):
        raise HTTPException(status_code=404, detail="License not found")
    return lic


def list_licenses_admin(db: Session, *, limit: int = 200, user_id: Optional[int] = None) -> list[DesktopLicense]:
    lim = max(1, min(int(limit), 500))
    q = select(DesktopLicense).options(selectinload(DesktopLicense.order)).order_by(DesktopLicense.id.desc())  # type: ignore[attr-defined]
    if user_id is not None:
        q = q.where(DesktopLicense.licensed_user_id == int(user_id))
    return list(db.execute(q.limit(lim)).scalars().all())


def reveal_license_key_for_user(
    db: Session,
    settings: Settings,
    *,
    user: CompanyUser,
    license_id: int,
) -> str:
    """Decrypt and return plaintext for owner only. Never logs plaintext."""
    lic = get_owned_license(db, user=user, license_id=license_id)
    return _decrypt_license_plaintext(db, settings, lic=lic, actor_type="user", actor_id=user.id)


def reveal_license_key_for_admin(
    db: Session,
    settings: Settings,
    *,
    admin: PlatformAdmin,
    license_id: int,
) -> str:
    """Explicit admin reveal — audited. Prefer masked views in normal admin UI."""
    lic = db.get(DesktopLicense, int(license_id))
    if not lic:
        raise HTTPException(status_code=404, detail="License not found")
    return _decrypt_license_plaintext(db, settings, lic=lic, actor_type="admin", actor_id=admin.id)


def _decrypt_license_plaintext(
    db: Session,
    settings: Settings,
    *,
    lic: DesktopLicense,
    actor_type: str,
    actor_id: int,
) -> str:
    if not lic.key_encrypted:
        raise HTTPException(status_code=503, detail="License key material is unavailable")
    try:
        plaintext = decrypt_license_key(lic.key_encrypted, settings.license_key_encryption_secret)
    except LicenseKeyEncryptionError as exc:
        raise HTTPException(
            status_code=503,
            detail="License key encryption secret is not configured or invalid",
        ) from exc
    if not plaintext:
        raise HTTPException(status_code=503, detail="License key could not be decrypted")
    # Audit without plaintext / ciphertext
    record_license_event(
        db,
        license_id=lic.id,
        actor_type=actor_type,
        actor_id=actor_id,
        event_type="license_key_revealed",
        meta={"license_id": lic.id, "seat_index": lic.seat_index, "order_id": lic.order_id},
    )
    db.flush()
    return plaintext


def ensure_email_delivery_pending(
    db: Session,
    *,
    order: DesktopOrder,
    user: CompanyUser,
) -> DesktopLicenseEmailDelivery:
    """Create or return the single per-order email delivery row (pending). Does not send."""
    existing = db.execute(
        select(DesktopLicenseEmailDelivery).where(DesktopLicenseEmailDelivery.order_id == int(order.id))
    ).scalar_one_or_none()
    if existing:
        return existing
    row = DesktopLicenseEmailDelivery(
        order_id=int(order.id),
        company_id=int(order.company_id),
        user_id=int(order.user_id),
        to_email=(user.email or "").strip(),
        status=LICENSE_EMAIL_PENDING,
        attempt_count=0,
    )
    db.add(row)
    db.flush()
    record_license_event(
        db,
        license_id=None,
        actor_type="system",
        actor_id=None,
        event_type="license_email_queued",
        meta={"order_id": order.id, "delivery_id": row.id},
    )
    return row


def _licenses_for_order(db: Session, order_id: int) -> list[DesktopLicense]:
    return list(
        db.execute(
            select(DesktopLicense)
            .where(DesktopLicense.order_id == int(order_id))
            .order_by(DesktopLicense.seat_index.asc(), DesktopLicense.id.asc())
        ).scalars().all()
    )


def build_license_email_body(
    *,
    customer_name: Optional[str],
    order: DesktopOrder,
    licenses: list[DesktopLicense],
    plaintexts: list[str],
    my_licenses_url: str,
) -> tuple[str, str]:
    """Return (subject, plain text). Includes keys for customer activation; no secrets/paths."""
    name = (customer_name or "").strip() or "Customer"
    subject = f"Your {order.product_name} license keys — {order.order_number}"
    lines = [
        f"Hello {name},",
        "",
        "Thank you for your purchase. Your license keys are ready.",
        "",
        f"Product: {order.product_name}",
        f"Plan: {order.plan_name}",
        f"Seats: {order.seats}",
        f"Order: {order.order_number}",
        "",
    ]
    for lic, key in zip(licenses, plaintexts):
        seat = lic.seat_index if lic.seat_index is not None else "?"
        exp = lic.expires_at.date().isoformat() if lic.expires_at else "n/a"
        lines.append(f"Seat {seat}")
        lines.append(f"  License key: {key}")
        lines.append(f"  Expires: {exp}")
        lines.append(f"  Status: Issued / Not activated")
        lines.append("")
    lines.extend(
        [
            "Activation:",
            "1. Install the desktop software for this product.",
            "2. When prompted, enter the license key for this computer.",
            "3. Each key activates one physical system for one product.",
            "",
            f"You can also view and reveal your keys in My Licenses: {my_licenses_url}",
            "",
            "If you did not make this purchase, contact support.",
            "",
            "— TheAIQualisys",
        ]
    )
    return subject, "\n".join(lines)


def _decrypt_all_for_email(
    settings: Settings, licenses: list[DesktopLicense]
) -> list[str]:
    keys: list[str] = []
    for lic in licenses:
        if not lic.key_encrypted:
            raise RuntimeError(f"License {lic.id} missing encrypted key material")
        pt = decrypt_license_key(lic.key_encrypted, settings.license_key_encryption_secret)
        if not pt:
            raise RuntimeError(f"License {lic.id} could not be decrypted for email")
        keys.append(pt)
    return keys


def _check_resend_rate(delivery: DesktopLicenseEmailDelivery, *, force_rate_check: bool) -> None:
    if not force_rate_check:
        return
    now = _utc_now()
    if delivery.last_attempted_at:
        last = delivery.last_attempted_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        elapsed = (now - last).total_seconds()
        if elapsed < LICENSE_EMAIL_RESEND_MIN_SECONDS:
            raise HTTPException(
                status_code=429,
                detail=f"Please wait {LICENSE_EMAIL_RESEND_MIN_SECONDS} seconds before resending",
            )
    # Hourly cap based on attempt_count window approximation via last hour attempts
    # (simple protection: refuse if attempt_count high and last attempt within hour)
    if delivery.attempt_count >= LICENSE_EMAIL_RESEND_MAX_ATTEMPTS_PER_HOUR and delivery.last_attempted_at:
        last = delivery.last_attempted_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if now - last < timedelta(hours=1):
            raise HTTPException(status_code=429, detail="Too many license email attempts; try again later")


def attempt_send_license_email_for_order(
    db: Session,
    settings: Settings,
    *,
    order_id: int,
    actor_type: str,
    actor_id: Optional[int],
    is_resend: bool = False,
    enforce_rate_limit: bool = False,
) -> DesktopLicenseEmailDelivery:
    """
    Send (or resend) license email for an order using already-minted licenses.
    Never creates licenses. Email failure updates status only — licenses stay valid.
    """
    order = db.execute(
        select(DesktopOrder).where(DesktopOrder.id == int(order_id)).with_for_update()
    ).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    licenses = _licenses_for_order(db, order.id)
    if not licenses:
        raise HTTPException(status_code=400, detail="No licenses exist for this order")

    user = db.get(CompanyUser, int(order.user_id))
    if not user or not (user.email or "").strip():
        raise HTTPException(status_code=400, detail="Customer email is unavailable")

    delivery = ensure_email_delivery_pending(db, order=order, user=user)
    _check_resend_rate(delivery, force_rate_check=enforce_rate_limit)

    delivery.to_email = user.email.strip()
    delivery.attempt_count = int(delivery.attempt_count or 0) + 1
    delivery.last_attempted_at = _utc_now()
    db.add(delivery)
    db.flush()

    event_type = "license_email_resent" if is_resend else "license_email_send_attempted"
    record_license_event(
        db,
        license_id=None,
        actor_type=actor_type,
        actor_id=actor_id,
        event_type=event_type,
        meta={
            "order_id": order.id,
            "delivery_id": delivery.id,
            "attempt_count": delivery.attempt_count,
            # never include keys
        },
    )

    if not is_email_configured(settings):
        delivery.status = LICENSE_EMAIL_FAILED
        delivery.last_error = "Email is not configured (RESEND_API_KEY/SMTP)"
        db.add(delivery)
        record_license_event(
            db,
            license_id=None,
            actor_type=actor_type,
            actor_id=actor_id,
            event_type="license_email_failed",
            meta={"order_id": order.id, "delivery_id": delivery.id, "error": "email_not_configured"},
        )
        db.flush()
        return delivery

    try:
        plaintexts = _decrypt_all_for_email(settings, licenses)
        base = (settings.public_app_url or "").rstrip("/") or "https://www.theaiqualisys.com"
        my_licenses_url = f"{base}/software/licenses"
        subject, body = build_license_email_body(
            customer_name=user.name,
            order=order,
            licenses=licenses,
            plaintexts=plaintexts,
            my_licenses_url=my_licenses_url,
        )
        # Discard plaintext references ASAP after send prep
        send_plain_text_email(settings, delivery.to_email, subject, body)
        del plaintexts
        delivery.status = LICENSE_EMAIL_SENT
        delivery.sent_at = _utc_now()
        delivery.last_error = None
        db.add(delivery)
        record_license_event(
            db,
            license_id=None,
            actor_type=actor_type,
            actor_id=actor_id,
            event_type="license_email_sent",
            meta={"order_id": order.id, "delivery_id": delivery.id, "seat_count": len(licenses)},
        )
    except LicenseKeyEncryptionError as exc:
        delivery.status = LICENSE_EMAIL_FAILED
        delivery.last_error = "encryption_secret_unavailable"
        db.add(delivery)
        record_license_event(
            db,
            license_id=None,
            actor_type=actor_type,
            actor_id=actor_id,
            event_type="license_email_failed",
            meta={"order_id": order.id, "delivery_id": delivery.id, "error": "encryption_secret_unavailable"},
        )
        # Do not raise — licenses remain valid; caller may surface soft failure
        del exc
    except Exception as exc:
        delivery.status = LICENSE_EMAIL_FAILED
        err = str(exc)[:500]
        delivery.last_error = err
        db.add(delivery)
        record_license_event(
            db,
            license_id=None,
            actor_type=actor_type,
            actor_id=actor_id,
            event_type="license_email_failed",
            meta={"order_id": order.id, "delivery_id": delivery.id, "error": "send_failed"},
        )
    db.flush()
    return delivery


def resend_license_email_for_customer(
    db: Session,
    settings: Settings,
    *,
    user: CompanyUser,
    order_id: int,
) -> DesktopLicenseEmailDelivery:
    order = db.execute(
        select(DesktopOrder).where(DesktopOrder.id == int(order_id), DesktopOrder.user_id == int(user.id))
    ).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if not _licenses_for_order(db, order.id):
        raise HTTPException(status_code=400, detail="No licenses to email for this order")
    return attempt_send_license_email_for_order(
        db,
        settings,
        order_id=order.id,
        actor_type="user",
        actor_id=user.id,
        is_resend=True,
        enforce_rate_limit=True,
    )


def resend_license_email_for_admin(
    db: Session,
    settings: Settings,
    *,
    admin: PlatformAdmin,
    order_id: int,
) -> DesktopLicenseEmailDelivery:
    order = db.get(DesktopOrder, int(order_id))
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if not _licenses_for_order(db, order.id):
        raise HTTPException(status_code=400, detail="No licenses to email for this order")
    return attempt_send_license_email_for_order(
        db,
        settings,
        order_id=order.id,
        actor_type="admin",
        actor_id=admin.id,
        is_resend=True,
        enforce_rate_limit=True,
    )


def get_email_delivery_for_customer_order(
    db: Session, *, user: CompanyUser, order_id: int
) -> Optional[DesktopLicenseEmailDelivery]:
    order = db.execute(
        select(DesktopOrder).where(DesktopOrder.id == int(order_id), DesktopOrder.user_id == int(user.id))
    ).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return db.execute(
        select(DesktopLicenseEmailDelivery).where(DesktopLicenseEmailDelivery.order_id == order.id)
    ).scalar_one_or_none()
