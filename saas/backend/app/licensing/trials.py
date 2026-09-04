"""Phase 7A: desktop software trial creation + trial-scoped email delivery.

Business rules (authoritative):
- One trial ever per (licensed_user_id, product_id) — DB partial unique index is authoritative.
- No company-wide trial cap.
- Separate trial allowed per product.
- Usable non-expired paid license blocks trial creation.
- No admin grant / no day-6 reminder / no trial→paid conversion.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.email_util import is_email_configured, send_plain_text_email
from app.licensing.constants import (
    ENTITLEMENT_PAID,
    ENTITLEMENT_TRIAL,
    LICENSE_EMAIL_FAILED,
    LICENSE_EMAIL_PENDING,
    LICENSE_EMAIL_RESEND_MAX_ATTEMPTS_PER_HOUR,
    LICENSE_EMAIL_RESEND_MIN_SECONDS,
    LICENSE_EMAIL_SENT,
    LICENSE_STATUS_ACTIVE,
    LICENSE_STATUS_ISSUED,
    TRIAL_CREATE_PER_IP_PER_HOUR,
    TRIAL_CREATE_PER_USER_PER_HOUR,
    TRIAL_CREATE_RATE_WINDOW_SECONDS,
    TRIAL_DURATION_DAYS,
    TRIAL_ERR_ALREADY_USED,
    TRIAL_ERR_BLOCKED_BY_PAID,
    TRIAL_ERR_INVALID_REQUEST,
    TRIAL_ERR_PRODUCT_INACTIVE,
    TRIAL_ERR_PRODUCT_NOT_FOUND,
    TRIAL_ERR_TRIAL_DISABLED,
    UQ_DESKTOP_LICENSES_ONE_TRIAL_PER_USER_PRODUCT,
)
from app.licensing.customer_licenses import masked_key_from_parts, serialize_license_public
from app.licensing.keys import LicenseKeyEncryptionError, decrypt_license_key
from app.licensing.models import (
    DesktopLicense,
    DesktopProduct,
    DesktopTrialEmailDelivery,
)
from app.licensing.rate_limit import check_rate_limit
from app.licensing.service import create_trial_license_row, record_license_event
from app.models import CompanyUser

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def trial_http_error(code: str, message: str, *, http_status: int) -> HTTPException:
    return HTTPException(
        status_code=http_status,
        detail={"code": code, "message": message},
    )


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


def is_trial_unique_conflict(exc: IntegrityError) -> bool:
    """True only for uq_desktop_licenses_one_trial_per_user_product — not other IntegrityErrors."""
    name = _integrity_constraint_name(exc)
    if name == UQ_DESKTOP_LICENSES_ONE_TRIAL_PER_USER_PRODUCT:
        return True
    text = _integrity_error_text(exc)
    return UQ_DESKTOP_LICENSES_ONE_TRIAL_PER_USER_PRODUCT in text


def _wall_clock_not_expired(lic: DesktopLicense, *, now: Optional[datetime] = None) -> bool:
    when = now or _utc_now()
    if lic.expires_at is None:
        return True
    exp = lic.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    return exp > when


def find_usable_paid_license(
    db: Session, *, licensed_user_id: int, product_id: int
) -> Optional[DesktopLicense]:
    """B4: issued/active paid license that has not wall-clock expired."""
    rows = db.execute(
        select(DesktopLicense).where(
            DesktopLicense.licensed_user_id == int(licensed_user_id),
            DesktopLicense.product_id == int(product_id),
            DesktopLicense.entitlement_type == ENTITLEMENT_PAID,
        )
    ).scalars().all()
    now = _utc_now()
    for lic in rows:
        status_l = (lic.status or "").lower()
        if status_l not in (LICENSE_STATUS_ISSUED, LICENSE_STATUS_ACTIVE):
            continue
        if _wall_clock_not_expired(lic, now=now):
            return lic
    return None


def find_any_trial_license(
    db: Session, *, licensed_user_id: int, product_id: int
) -> Optional[DesktopLicense]:
    """B1: any trial row permanently consumes eligibility."""
    return db.execute(
        select(DesktopLicense).where(
            DesktopLicense.licensed_user_id == int(licensed_user_id),
            DesktopLicense.product_id == int(product_id),
            DesktopLicense.entitlement_type == ENTITLEMENT_TRIAL,
        )
    ).scalar_one_or_none()


def resolve_trial_product(db: Session, product_code: str) -> DesktopProduct:
    code = (product_code or "").strip().upper()
    if not code:
        raise trial_http_error(
            TRIAL_ERR_INVALID_REQUEST,
            "product_code is required",
            http_status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    product = db.execute(
        select(DesktopProduct).where(DesktopProduct.code == code)
    ).scalar_one_or_none()
    if product is None:
        raise trial_http_error(
            TRIAL_ERR_PRODUCT_NOT_FOUND,
            "Product not found",
            http_status=status.HTTP_404_NOT_FOUND,
        )
    if not bool(product.listing_active):
        raise trial_http_error(
            TRIAL_ERR_PRODUCT_INACTIVE,
            "This product is not available",
            http_status=status.HTTP_400_BAD_REQUEST,
        )
    if not bool(product.trial_enabled):
        raise trial_http_error(
            TRIAL_ERR_TRIAL_DISABLED,
            "Trials are disabled for this product",
            http_status=status.HTTP_400_BAD_REQUEST,
        )
    return product


def apply_trial_create_rate_limits(*, user_id: int, client_ip: str) -> None:
    """
    In-process sliding-window limits (not distributed across workers).
    Prefer edge/API-gateway or Redis limits for multi-worker production.
    """
    check_rate_limit(
        scope="trial_create_user",
        key=str(int(user_id)),
        limit=TRIAL_CREATE_PER_USER_PER_HOUR,
        window_seconds=TRIAL_CREATE_RATE_WINDOW_SECONDS,
    )
    check_rate_limit(
        scope="trial_create_ip",
        key=(client_ip or "unknown").strip() or "unknown",
        limit=TRIAL_CREATE_PER_IP_PER_HOUR,
        window_seconds=TRIAL_CREATE_RATE_WINDOW_SECONDS,
    )


def _assert_eligible_for_trial(
    db: Session, *, user: CompanyUser, product: DesktopProduct
) -> None:
    if find_usable_paid_license(db, licensed_user_id=int(user.id), product_id=int(product.id)):
        raise trial_http_error(
            TRIAL_ERR_BLOCKED_BY_PAID,
            "An active paid license already exists for this product",
            http_status=status.HTTP_409_CONFLICT,
        )
    if find_any_trial_license(db, licensed_user_id=int(user.id), product_id=int(product.id)):
        record_license_event(
            db,
            license_id=None,
            actor_type="user",
            actor_id=int(user.id),
            event_type="trial_denied_duplicate",
            meta={"product_id": int(product.id), "product_code": product.code, "reason": "already_used"},
        )
        raise trial_http_error(
            TRIAL_ERR_ALREADY_USED,
            "A trial for this product has already been used",
            http_status=status.HTTP_409_CONFLICT,
        )


def _queue_trial_email_delivery(
    db: Session, *, license_row: DesktopLicense, user: CompanyUser
) -> DesktopTrialEmailDelivery:
    delivery = DesktopTrialEmailDelivery(
        license_id=int(license_row.id),
        company_id=int(license_row.company_id),
        user_id=int(user.id),
        to_email=(user.email or "").strip() or "unknown@invalid",
        status=LICENSE_EMAIL_PENDING,
        attempt_count=0,
    )
    db.add(delivery)
    db.flush()
    return delivery


def create_desktop_trial(
    db: Session,
    settings: Settings,
    *,
    user: CompanyUser,
    product_code: str,
) -> tuple[DesktopLicense, DesktopProduct, DesktopTrialEmailDelivery]:
    """
    Create a trial license inside the caller's transaction boundary.

    Caller must commit, then call attempt_send_trial_email (email failure must not
    roll back the license).
    """
    product = resolve_trial_product(db, product_code)
    _assert_eligible_for_trial(db, user=user, product=product)

    duration = int(product.trial_duration_days or 0) or int(TRIAL_DURATION_DAYS)
    try:
        license_row, _plaintext = create_trial_license_row(
            db,
            settings,
            product_id=int(product.id),
            company_id=int(user.company_id),
            licensed_user_id=int(user.id),
            duration_days=duration,
        )
        # Discard plaintext immediately — deliver via email/reveal only
        del _plaintext
        delivery = _queue_trial_email_delivery(db, license_row=license_row, user=user)
        db.flush()
        return license_row, product, delivery
    except IntegrityError as exc:
        if is_trial_unique_conflict(exc):
            raise trial_http_error(
                TRIAL_ERR_ALREADY_USED,
                "A trial for this product has already been used",
                http_status=status.HTTP_409_CONFLICT,
            ) from exc
        raise


def build_trial_email_body(
    *,
    customer_name: Optional[str],
    product: DesktopProduct,
    license_row: DesktopLicense,
    plaintext_key: str,
    my_licenses_url: str,
) -> tuple[str, str]:
    name = (customer_name or "").strip() or "Customer"
    exp = license_row.expires_at.date().isoformat() if license_row.expires_at else "n/a"
    masked = masked_key_from_parts(license_row.key_prefix, license_row.key_last4)
    subject = f"Your {product.name} 7-day trial is ready"
    body = "\n".join(
        [
            f"Hello {name},",
            "",
            f"Your free trial for {product.name} is ready.",
            "",
            f"Product: {product.name}",
            f"Trial expires: {exp}",
            f"License key (masked): {masked}",
            "",
            f"License key: {plaintext_key}",
            "",
            "Activation:",
            "1. Download and install the desktop software for this product.",
            "2. When prompted, enter the license key on this computer.",
            "3. Each trial key activates one physical system for one product.",
            "4. After the trial ends, purchase a full license to continue — the paid key is separate.",
            "",
            f"View and reveal your key anytime in My Licenses: {my_licenses_url}",
            "",
            "If you did not request this trial, contact support.",
            "",
            "— TheAIQualisys",
        ]
    )
    return subject, body


def _check_trial_resend_rate(delivery: DesktopTrialEmailDelivery, *, force_rate_check: bool) -> None:
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
    if delivery.attempt_count >= LICENSE_EMAIL_RESEND_MAX_ATTEMPTS_PER_HOUR and delivery.last_attempted_at:
        last = delivery.last_attempted_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if now - last < timedelta(hours=1):
            raise HTTPException(status_code=429, detail="Too many trial email attempts; try again later")


def attempt_send_trial_email(
    db: Session,
    settings: Settings,
    *,
    license_id: int,
    actor_type: str,
    actor_id: Optional[int],
    is_resend: bool = False,
    enforce_rate_limit: bool = False,
) -> DesktopTrialEmailDelivery:
    """
    Send (or resend) trial email for an already-minted trial license.
    Never remints. Email failure updates delivery status only.
    """
    license_row = db.execute(
        select(DesktopLicense).where(DesktopLicense.id == int(license_id)).with_for_update()
    ).scalar_one_or_none()
    if not license_row or (license_row.entitlement_type or "").lower() != ENTITLEMENT_TRIAL:
        raise HTTPException(status_code=404, detail="Trial license not found")

    product = db.get(DesktopProduct, int(license_row.product_id))
    if product is None:
        raise HTTPException(status_code=400, detail="Product unavailable for trial email")

    user = db.get(CompanyUser, int(license_row.licensed_user_id))
    if not user or not (user.email or "").strip():
        raise HTTPException(status_code=400, detail="Customer email is unavailable")

    delivery = db.execute(
        select(DesktopTrialEmailDelivery)
        .where(DesktopTrialEmailDelivery.license_id == int(license_id))
        .with_for_update()
    ).scalar_one_or_none()
    if delivery is None:
        delivery = DesktopTrialEmailDelivery(
            license_id=int(license_id),
            company_id=int(license_row.company_id),
            user_id=int(user.id),
            to_email=user.email.strip(),
            status=LICENSE_EMAIL_PENDING,
            attempt_count=0,
        )
        db.add(delivery)
        db.flush()

    _check_trial_resend_rate(delivery, force_rate_check=enforce_rate_limit)

    delivery.to_email = user.email.strip()
    delivery.attempt_count = int(delivery.attempt_count or 0) + 1
    delivery.last_attempted_at = _utc_now()
    db.add(delivery)
    db.flush()

    event_type = "trial_email_resent" if is_resend else "trial_email_send_attempted"
    record_license_event(
        db,
        license_id=int(license_id),
        actor_type=actor_type,
        actor_id=actor_id,
        event_type=event_type,
        meta={"delivery_id": delivery.id, "attempt_count": delivery.attempt_count},
    )

    if not is_email_configured(settings):
        delivery.status = LICENSE_EMAIL_FAILED
        delivery.last_error = "Email is not configured (RESEND_API_KEY/SMTP)"
        db.add(delivery)
        record_license_event(
            db,
            license_id=int(license_id),
            actor_type=actor_type,
            actor_id=actor_id,
            event_type="trial_email_failed",
            meta={"delivery_id": delivery.id, "error": "email_not_configured"},
        )
        db.flush()
        return delivery

    try:
        if not license_row.key_encrypted:
            raise RuntimeError("Trial license missing encrypted key material")
        plaintext = decrypt_license_key(
            license_row.key_encrypted, settings.license_key_encryption_secret
        )
        if not plaintext:
            raise RuntimeError("Trial license could not be decrypted for email")
        base = (settings.public_app_url or "").rstrip("/") or "https://www.theaiqualisys.com"
        my_licenses_url = f"{base}/software/licenses"
        subject, body = build_trial_email_body(
            customer_name=user.name,
            product=product,
            license_row=license_row,
            plaintext_key=plaintext,
            my_licenses_url=my_licenses_url,
        )
        del plaintext
        send_plain_text_email(settings, delivery.to_email, subject, body)
        delivery.status = LICENSE_EMAIL_SENT
        delivery.sent_at = _utc_now()
        delivery.last_error = None
        db.add(delivery)
        record_license_event(
            db,
            license_id=int(license_id),
            actor_type=actor_type,
            actor_id=actor_id,
            event_type="trial_email_sent",
            meta={"delivery_id": delivery.id},
        )
    except LicenseKeyEncryptionError:
        delivery.status = LICENSE_EMAIL_FAILED
        delivery.last_error = "encryption_secret_unavailable"
        db.add(delivery)
        record_license_event(
            db,
            license_id=int(license_id),
            actor_type=actor_type,
            actor_id=actor_id,
            event_type="trial_email_failed",
            meta={"delivery_id": delivery.id, "error": "encryption_secret_unavailable"},
        )
    except Exception:
        delivery.status = LICENSE_EMAIL_FAILED
        delivery.last_error = "send_failed"
        db.add(delivery)
        record_license_event(
            db,
            license_id=int(license_id),
            actor_type=actor_type,
            actor_id=actor_id,
            event_type="trial_email_failed",
            meta={"delivery_id": delivery.id, "error": "send_failed"},
        )
        logger.warning("trial email send failed license_id=%s", license_id)
    db.flush()
    return delivery


def serialize_trial_create_response(
    license_row: DesktopLicense, *, product: DesktopProduct
) -> dict[str, Any]:
    """Masked license payload — never includes plaintext or ciphertext."""
    return serialize_license_public(license_row, product=product)
