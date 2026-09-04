"""Phase 4: manual UPI payment submission, admin approve/reject, license minting.

Approval mints N independent licenses (order.seats). No device binding.
Idempotent: repeated approval does not mint again.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.config import Settings
from app.licensing.constants import (
    ORDER_STATUS_APPROVED,
    ORDER_STATUS_PAYMENT_SUBMITTED,
    ORDER_STATUS_PENDING_PAYMENT,
    ORDER_STATUS_REJECTED,
    PAYMENT_SCREENSHOT_ALLOWED_MIME,
    PAYMENT_SCREENSHOT_MAX_BYTES,
    PAYMENT_STATUS_APPROVED,
    PAYMENT_STATUS_PENDING_REVIEW,
    PAYMENT_STATUS_REJECTED,
)
from app.licensing.models import (
    DesktopLicense,
    DesktopOrder,
    DesktopPayment,
    DesktopUpiSettings,
)
from app.licensing.service import create_paid_licenses_for_seats, record_license_event
from app.models import CompanyUser, PlatformAdmin

_UTR_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-\s]{5,63}$")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def get_or_create_upi_settings(db: Session, settings: Settings) -> DesktopUpiSettings:
    row = db.get(DesktopUpiSettings, 1)
    if row:
        return row
    row = DesktopUpiSettings(
        id=1,
        upi_id=(settings.upi_id or "").strip(),
        payee_name="",
        instructions=(
            "Pay the order total via UPI using the details below, then submit your UTR / UPI "
            "reference. License keys are issued only after an admin verifies your payment."
        ),
    )
    db.add(row)
    db.flush()
    return row


def serialize_upi_settings(row: DesktopUpiSettings, *, include_admin: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {
        "upi_id": row.upi_id or "",
        "payee_name": row.payee_name or "",
        "instructions": row.instructions,
        "has_qr_image": bool(row.qr_image_path),
    }
    if include_admin:
        out["qr_image_path"] = row.qr_image_path
        out["updated_at"] = row.updated_at.isoformat() if row.updated_at else None
    return out


def update_upi_settings(
    db: Session,
    *,
    admin: PlatformAdmin,
    upi_id: str,
    payee_name: str,
    instructions: Optional[str],
    qr_image_path: Optional[str] = None,
    clear_qr: bool = False,
) -> DesktopUpiSettings:
    row = db.get(DesktopUpiSettings, 1)
    if not row:
        row = DesktopUpiSettings(id=1, upi_id="", payee_name="")
        db.add(row)
        db.flush()
    upi = (upi_id or "").strip()
    payee = (payee_name or "").strip()
    if not upi:
        raise HTTPException(status_code=400, detail="upi_id is required")
    if not payee:
        raise HTTPException(status_code=400, detail="payee_name is required")
    row.upi_id = upi
    row.payee_name = payee
    if instructions is not None:
        row.instructions = instructions.strip() or None
    if clear_qr:
        row.qr_image_path = None
    elif qr_image_path is not None:
        row.qr_image_path = qr_image_path
    row.updated_by_admin_id = admin.id
    row.updated_at = _utc_now()
    db.add(row)
    db.flush()
    return row


def serialize_payment(payment: DesktopPayment) -> dict[str, Any]:
    return {
        "id": payment.id,
        "order_id": payment.order_id,
        "upi_id": payment.upi_id,
        "amount_inr": payment.amount_inr,
        "reference_note": payment.reference_note,
        "has_screenshot": bool(payment.screenshot_path),
        "screenshot_mime": payment.screenshot_mime,
        "status": payment.status,
        "reviewed_by_admin_id": payment.reviewed_by_admin_id,
        "reviewed_at": payment.reviewed_at.isoformat() if payment.reviewed_at else None,
        "review_note": payment.review_note,
        "created_at": payment.created_at.isoformat() if payment.created_at else None,
    }


async def save_payment_screenshot(
    *,
    upload_root: Path,
    company_id: int,
    order_id: int,
    file: UploadFile,
) -> tuple[str, str]:
    """Validate and store screenshot; returns (relative_path, mime)."""
    mime = (file.content_type or "").lower().strip()
    if mime == "image/jpg":
        mime = "image/jpeg"
    if mime not in PAYMENT_SCREENSHOT_ALLOWED_MIME:
        raise HTTPException(status_code=400, detail="Screenshot must be JPEG, PNG, or WebP")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty screenshot upload")
    if len(data) > PAYMENT_SCREENSHOT_MAX_BYTES:
        raise HTTPException(status_code=400, detail="Screenshot exceeds 5 MB limit")
    ext = {".jpeg": "jpg", "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}.get(mime, "bin")
    if mime == "image/jpeg":
        ext = "jpg"
    elif mime == "image/png":
        ext = "png"
    elif mime == "image/webp":
        ext = "webp"
    rel = Path("desktop_payments") / str(company_id) / f"order_{order_id}_{uuid.uuid4().hex[:12]}.{ext}"
    dest = upload_root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return str(rel).replace("\\", "/"), mime


def submit_payment_for_order(
    db: Session,
    settings: Settings,
    *,
    user: CompanyUser,
    order_id: int,
    utr_reference: str,
    screenshot_path: Optional[str] = None,
    screenshot_mime: Optional[str] = None,
) -> DesktopPayment:
    """Customer submits UTR; does NOT mark paid. Status = pending_review."""
    utr = (utr_reference or "").strip()
    if not utr or not _UTR_RE.match(utr):
        raise HTTPException(
            status_code=400,
            detail="A valid UTR / UPI payment reference is required (6–64 alphanumeric characters)",
        )

    order = db.execute(
        select(DesktopOrder).where(DesktopOrder.id == int(order_id)).with_for_update()
    ).scalar_one_or_none()
    if not order or int(order.user_id) != int(user.id):
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status == ORDER_STATUS_APPROVED:
        raise HTTPException(status_code=409, detail="Order is already approved")
    if order.status not in (ORDER_STATUS_PENDING_PAYMENT, ORDER_STATUS_REJECTED, ORDER_STATUS_PAYMENT_SUBMITTED):
        raise HTTPException(status_code=400, detail=f"Order status '{order.status}' cannot accept payment")

    # Block if a pending_review already exists
    existing_pending = db.execute(
        select(DesktopPayment).where(
            DesktopPayment.order_id == order.id,
            DesktopPayment.status == PAYMENT_STATUS_PENDING_REVIEW,
        )
    ).scalar_one_or_none()
    if existing_pending:
        raise HTTPException(
            status_code=409,
            detail="A payment is already pending admin review for this order",
        )

    upi = get_or_create_upi_settings(db, settings)
    payment = DesktopPayment(
        order_id=order.id,
        upi_id=upi.upi_id or settings.upi_id,
        amount_inr=int(order.total_price_inr),  # server-side amount only
        reference_note=utr,
        screenshot_path=screenshot_path,
        screenshot_mime=screenshot_mime,
        status=PAYMENT_STATUS_PENDING_REVIEW,
    )
    db.add(payment)
    order.status = ORDER_STATUS_PAYMENT_SUBMITTED
    db.add(order)
    db.flush()
    record_license_event(
        db,
        license_id=None,
        actor_type="user",
        actor_id=user.id,
        event_type="payment_submitted",
        meta={"order_id": order.id, "payment_id": payment.id, "amount_inr": payment.amount_inr},
    )
    return payment


def list_pending_payment_requests(db: Session, *, limit: int = 200) -> list[tuple[DesktopPayment, DesktopOrder]]:
    lim = max(1, min(int(limit), 500))
    rows = db.execute(
        select(DesktopPayment)
        .options(selectinload(DesktopPayment.order))
        .where(DesktopPayment.status == PAYMENT_STATUS_PENDING_REVIEW)
        .order_by(DesktopPayment.id.asc())
        .limit(lim)
    ).scalars().all()
    return [(p, p.order) for p in rows]


def list_payment_requests(
    db: Session, *, status: Optional[str] = None, limit: int = 200
) -> list[DesktopPayment]:
    lim = max(1, min(int(limit), 500))
    q = select(DesktopPayment).options(selectinload(DesktopPayment.order)).order_by(DesktopPayment.id.desc())
    if status:
        q = q.where(DesktopPayment.status == status)
    return list(db.execute(q.limit(lim)).scalars().all())


def count_licenses_for_order(db: Session, order_id: int) -> int:
    return int(
        db.execute(
            select(func.count()).select_from(DesktopLicense).where(DesktopLicense.order_id == int(order_id))
        ).scalar_one()
        or 0
    )


def approve_payment_and_mint_licenses(
    db: Session,
    settings: Settings,
    *,
    admin: PlatformAdmin,
    payment_id: int,
) -> tuple[DesktopPayment, DesktopOrder, list[DesktopLicense]]:
    """
    Approve payment and mint exactly order.seats independent licenses.
    Idempotent / concurrent-safe via order row lock + unique (order_id, seat_index).
    """
    payment = db.execute(
        select(DesktopPayment).where(DesktopPayment.id == int(payment_id)).with_for_update()
    ).scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    order = db.execute(
        select(DesktopOrder).where(DesktopOrder.id == payment.order_id).with_for_update()
    ).scalar_one()

    if payment.status == PAYMENT_STATUS_APPROVED or order.status == ORDER_STATUS_APPROVED:
        raise HTTPException(
            status_code=409,
            detail="Payment/order already approved; licenses were not minted again",
        )
    if payment.status != PAYMENT_STATUS_PENDING_REVIEW:
        raise HTTPException(status_code=400, detail=f"Payment status '{payment.status}' cannot be approved")

    existing = count_licenses_for_order(db, order.id)
    if existing > 0:
        # Partial mint from a failed prior attempt — refuse silent remint
        raise HTTPException(
            status_code=409,
            detail=f"Order already has {existing} license(s); refusing duplicate mint",
        )

    seats = int(order.seats)
    if seats < 1:
        raise HTTPException(status_code=400, detail="Order seats invalid")

    # Amount must match server snapshot (never trust client)
    if int(payment.amount_inr) != int(order.total_price_inr):
        raise HTTPException(status_code=400, detail="Payment amount does not match order total")

    minted = create_paid_licenses_for_seats(
        db,
        settings,
        product_id=int(order.product_id),
        plan_id=int(order.plan_id),
        order_id=int(order.id),
        company_id=int(order.company_id),
        licensed_user_id=int(order.user_id),
        seat_count=seats,
        duration_days=int(order.duration_days),
        created_by_admin_id=int(admin.id),
    )
    licenses = [row for row, _plaintext in minted]
    # Discard plaintext here — Phase 5 email/reveal; do not return keys in Phase 4 admin response by default

    payment.status = PAYMENT_STATUS_APPROVED
    payment.reviewed_by_admin_id = admin.id
    payment.reviewed_at = _utc_now()
    order.status = ORDER_STATUS_APPROVED
    db.add(payment)
    db.add(order)
    record_license_event(
        db,
        license_id=None,
        actor_type="admin",
        actor_id=admin.id,
        event_type="payment_approved_licenses_minted",
        meta={
            "order_id": order.id,
            "payment_id": payment.id,
            "seats": seats,
            "license_ids": [lic.id for lic in licenses],
        },
    )
    db.flush()
    return payment, order, licenses


def reject_payment(
    db: Session,
    *,
    admin: PlatformAdmin,
    payment_id: int,
    reason: str,
) -> tuple[DesktopPayment, DesktopOrder]:
    reason = (reason or "").strip()
    if len(reason) < 3:
        raise HTTPException(status_code=400, detail="Rejection reason is required")

    payment = db.execute(
        select(DesktopPayment).where(DesktopPayment.id == int(payment_id)).with_for_update()
    ).scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.status != PAYMENT_STATUS_PENDING_REVIEW:
        raise HTTPException(status_code=400, detail=f"Payment status '{payment.status}' cannot be rejected")

    order = db.execute(
        select(DesktopOrder).where(DesktopOrder.id == payment.order_id).with_for_update()
    ).scalar_one()
    if order.status == ORDER_STATUS_APPROVED:
        raise HTTPException(status_code=409, detail="Cannot reject payment for an approved order")

    payment.status = PAYMENT_STATUS_REJECTED
    payment.reviewed_by_admin_id = admin.id
    payment.reviewed_at = _utc_now()
    payment.review_note = reason
    # Allow customer to resubmit
    order.status = ORDER_STATUS_PENDING_PAYMENT
    db.add(payment)
    db.add(order)
    record_license_event(
        db,
        license_id=None,
        actor_type="admin",
        actor_id=admin.id,
        event_type="payment_rejected",
        meta={"order_id": order.id, "payment_id": payment.id, "reason": reason},
    )
    db.flush()
    return payment, order


def list_customer_payments_for_order(db: Session, *, user: CompanyUser, order_id: int) -> list[DesktopPayment]:
    order = db.execute(
        select(DesktopOrder).where(DesktopOrder.id == int(order_id), DesktopOrder.user_id == int(user.id))
    ).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return list(
        db.execute(
            select(DesktopPayment)
            .where(DesktopPayment.order_id == order.id)
            .order_by(DesktopPayment.id.desc())
        )
        .scalars()
        .all()
    )
