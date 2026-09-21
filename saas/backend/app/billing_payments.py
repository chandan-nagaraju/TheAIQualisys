"""SaaS billing payments: customer Payment Done + Platform Admin verify/reject.

Does not generate invoices or activate subscriptions.
Desktop license payments stay in desktop_payments.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.billing_period import (
    billing_total_inr,
    normalize_billing_period,
    period_duration,
    period_label,
)
from app.config import Settings, get_settings
from app.models import AdminNotification, BillingPayment, Company, CompanyUser, PlatformAdmin
from app.pricing_catalog import get_pricing_by_module_name, list_fir_plan_rows

STATUS_PENDING = "pending_verification"
STATUS_VERIFIED = "verified"
STATUS_REJECTED = "rejected"
ALLOWED_STATUSES = {STATUS_PENDING, STATUS_VERIFIED, STATUS_REJECTED, "pending"}

REJECT_REASONS = (
    "payment_not_received",
    "incorrect_amount",
    "screenshot_mismatch",
    "transaction_not_found",
    "wrong_account",
    "other",
)

REJECT_REASON_LABELS = {
    "payment_not_received": "Payment not received",
    "incorrect_amount": "Incorrect amount",
    "screenshot_mismatch": "Screenshot does not match",
    "transaction_not_found": "Transaction not found",
    "wrong_account": "Wrong account",
    "other": "Other",
}

MODULE_FIR = "fir"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def payment_code_for(payment_id: int) -> str:
    return f"PAY-{payment_id:05d}"


def _is_enterprise(plan_type: str, plan_name: str) -> bool:
    t = (plan_type or "").strip().lower()
    n = (plan_name or "").strip().lower()
    return t == "enterprise" or "enterprise" in n


def _primary_user(company: Company | None) -> CompanyUser | None:
    if not company or not company.users:
        return None
    return sorted(company.users, key=lambda u: u.id)[0]


def resolve_catalog_quote(
    db: Session,
    *,
    module_key: str,
    plan_type: str | None,
) -> dict[str, Any]:
    """Server-side catalog lookup. Never trusts client amount/name."""
    key = (module_key or MODULE_FIR).strip().lower() or MODULE_FIR
    if key in (MODULE_FIR, "final_inspection", "inspection"):
        want = (plan_type or "").strip().lower()
        if not want:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Plan is required")
        rows = list_fir_plan_rows(db)
        row = next((r for r in rows if (r.fir_plan_type or "").lower() == want), None)
        if not row:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown FIR plan")
        return {
            "module_key": MODULE_FIR,
            "module_label": "FIR",
            "plan_type": row.fir_plan_type or want,
            "plan_name": row.display_name,
            "monthly_price": int(row.monthly_price),
            "yearly_price": int(row.yearly_price) if row.yearly_price is not None else None,
            "catalog_id": row.id,
            "enterprise": _is_enterprise(row.fir_plan_type or "", row.display_name),
        }

    row = get_pricing_by_module_name(db, key)
    if not row or row.fir_plan_type:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown module")
    return {
        "module_key": row.module_name,
        "module_label": row.display_name,
        "plan_type": row.module_name,
        "plan_name": row.display_name,
        "monthly_price": int(row.monthly_price),
        "yearly_price": int(row.yearly_price) if row.yearly_price is not None else None,
        "catalog_id": row.id,
        "enterprise": False,
    }


def quote_payment(db: Session, *, module_key: str, plan_type: str | None, billing_period_raw: str) -> dict[str, Any]:
    period = normalize_billing_period(billing_period_raw)
    cat = resolve_catalog_quote(db, module_key=module_key, plan_type=plan_type)
    amount = billing_total_inr(
        cat["monthly_price"],
        period,
        enterprise=cat["enterprise"],
        yearly_price=cat["yearly_price"] if period == "YEARLY" else None,
    )
    return {
        **cat,
        "billing_period": period,
        "billing_period_label": period_label(period),
        "subscription_duration": period_duration(period),
        "amount_inr": amount,
        "currency": "INR",
        "payment_method": "UPI",
    }


def whatsapp_digits(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    return "".join(ch for ch in (settings.whatsapp_number or "") if ch.isdigit())


def whatsapp_url_for_message(message: str, settings: Settings | None = None) -> str:
    phone = whatsapp_digits(settings)
    if len(phone) < 10:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="WhatsApp number is not configured. Set WHATSAPP_NUMBER on the backend.",
        )
    return f"https://wa.me/{phone}?text={quote(message)}"


def customer_whatsapp_message(row: BillingPayment, user: CompanyUser | None, company: Company | None) -> str:
    name = row.customer_name_snapshot or (user.name if user and user.name else None) or (company.company_name if company else "Customer")
    lines = [
        "Hello TheAIQualisys,",
        "",
        "I have completed my subscription payment.",
        "",
        f"Customer: {name}",
        f"Module: {row.module_label or row.module_key or 'FIR'}",
        f"Plan: {row.plan_name}",
        f"Billing Period: {period_label(row.billing_period or 'MONTHLY')}",
        f"Amount: ₹{row.amount_inr}",
    ]
    if row.payment_code:
        lines.append(f"Payment Reference: {row.payment_code}")
    lines.extend(["", "I am sending the payment screenshot for verification."])
    return "\n".join(lines)


def serialize_billing_payment(row: BillingPayment, *, settings: Settings | None = None) -> dict[str, Any]:
    company = row.company
    user = row.user or _primary_user(company)
    st = row.status if row.status != "pending" else STATUS_PENDING
    snap = row.pricing_snapshot if isinstance(row.pricing_snapshot, dict) else {}
    code = row.payment_code or (payment_code_for(row.id) if row.id else None)
    phone_digits = None
    try:
        phone_digits = whatsapp_digits(settings)
    except Exception:
        phone_digits = None
    submitted = row.payment_submitted_at or row.payment_date
    return {
        "id": row.id,
        "payment_code": code,
        "company_id": row.company_id,
        "user_id": row.user_id,
        "customer_id": row.user_id,
        "customer_name": row.customer_name_snapshot
        or ((user.name if user and user.name else None) or (company.company_name if company else None)),
        "company_name": row.company_name_snapshot or (company.company_name if company else None),
        "email": row.email_snapshot or (user.email if user else None),
        "phone": None,
        "billing_address": None,
        "city": None,
        "state": None,
        "state_code": None,
        "pincode": None,
        "gstin": None,
        "module_key": row.module_key or MODULE_FIR,
        "module_label": row.module_label or "FIR",
        "subscription_plan": row.plan_name,
        "plan_type": row.plan_type or row.plan_name,
        "plan_id": snap.get("catalog_id"),
        "billing_period": row.billing_period or "MONTHLY",
        "billing_period_label": period_label(row.billing_period or "MONTHLY"),
        "subscription_duration": row.subscription_duration or period_duration(row.billing_period or "MONTHLY"),
        "subscription_start": company.subscription_start.isoformat() if company and company.subscription_start else None,
        "subscription_end": company.subscription_end.isoformat() if company and company.subscription_end else None,
        "amount_inr": row.amount_inr,
        "currency": row.currency or "INR",
        "original_plan_price": snap.get("monthly_price") or snap.get("original_plan_price"),
        "payment_method": row.payment_method,
        "reference_note": row.reference_note or code,
        "payment_date": row.payment_date.isoformat() if row.payment_date else None,
        "payment_submitted_at": submitted.isoformat() if submitted else None,
        "status": st,
        "has_proof": bool(row.proof_path),
        "pricing_snapshot": snap or None,
        "verified_at": row.verified_at.isoformat() if row.verified_at else None,
        "rejected_at": row.rejected_at.isoformat() if row.rejected_at else None,
        "rejection_reason": row.rejection_reason,
        "rejection_reason_label": REJECT_REASON_LABELS.get(row.rejection_reason or "", row.rejection_reason),
        "whatsapp_number": phone_digits,
        "whatsapp_url": f"https://wa.me/{phone_digits}" if phone_digits and len(phone_digits) >= 10 else None,
    }


def billing_payment_counts(db: Session) -> dict[str, int]:
    rows = db.execute(select(BillingPayment.status, func.count(BillingPayment.id)).group_by(BillingPayment.status)).all()
    counts = {STATUS_PENDING: 0, STATUS_VERIFIED: 0, STATUS_REJECTED: 0}
    for status_val, n in rows:
        key = STATUS_PENDING if status_val in (STATUS_PENDING, "pending") else status_val
        if key in counts:
            counts[key] += int(n)
    return counts


def list_billing_payments(db: Session, *, status_filter: str | None = None, limit: int = 500) -> list[BillingPayment]:
    q = select(BillingPayment).options(
        selectinload(BillingPayment.company).selectinload(Company.users),
        selectinload(BillingPayment.user),
    )
    if status_filter:
        want = status_filter if status_filter != "pending" else STATUS_PENDING
        if want not in {STATUS_PENDING, STATUS_VERIFIED, STATUS_REJECTED}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payment status")
        if want == STATUS_PENDING:
            q = q.where(or_(BillingPayment.status == STATUS_PENDING, BillingPayment.status == "pending"))
        else:
            q = q.where(BillingPayment.status == want)
    q = q.order_by(
        func.coalesce(BillingPayment.payment_submitted_at, BillingPayment.payment_date).desc(),
        BillingPayment.id.desc(),
    ).limit(limit)
    return list(db.execute(q).scalars().all())


def get_billing_payment(db: Session, payment_id: int) -> BillingPayment:
    row = db.execute(
        select(BillingPayment)
        .options(
            selectinload(BillingPayment.company).selectinload(Company.users),
            selectinload(BillingPayment.user),
        )
        .where(BillingPayment.id == payment_id)
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
    return row


def _find_pending(
    db: Session,
    *,
    company_id: int,
    module_key: str,
    plan_type: str,
    billing_period: str,
) -> BillingPayment | None:
    return db.execute(
        select(BillingPayment)
        .options(
            selectinload(BillingPayment.company).selectinload(Company.users),
            selectinload(BillingPayment.user),
        )
        .where(
            BillingPayment.company_id == company_id,
            BillingPayment.module_key == module_key,
            BillingPayment.plan_type == plan_type,
            BillingPayment.billing_period == billing_period,
            or_(BillingPayment.status == STATUS_PENDING, BillingPayment.status == "pending"),
        )
        .order_by(BillingPayment.id.desc())
    ).scalars().first()


def _notify_admins(db: Session, row: BillingPayment, user: CompanyUser, company: Company) -> None:
    name = row.customer_name_snapshot or user.name or company.company_name
    period = period_label(row.billing_period or "MONTHLY")
    module = row.module_label or "FIR"
    msg = (
        f"{name} has marked a payment as completed for {module} – {row.plan_name} – {period} "
        f"(₹{row.amount_inr}). Please check WhatsApp and verify the payment."
    )
    db.add(
        AdminNotification(
            title="Payment Verification Required",
            message=msg,
            link_path=f"/admin/billing/payments/{row.id}",
            payment_id=row.id,
            is_read=0,
        )
    )


def submit_payment_done(
    db: Session,
    *,
    user: CompanyUser,
    company: Company,
    module_key: str,
    plan_type: str | None,
    billing_period_raw: str,
    settings: Settings | None = None,
) -> tuple[BillingPayment, bool]:
    """Create or reuse a pending verification record. Returns (row, already_submitted)."""
    quote = quote_payment(db, module_key=module_key, plan_type=plan_type, billing_period_raw=billing_period_raw)
    existing = _find_pending(
        db,
        company_id=company.id,
        module_key=quote["module_key"],
        plan_type=quote["plan_type"],
        billing_period=quote["billing_period"],
    )
    if existing:
        return existing, True

    now = _utc_now()
    customer_name = user.name or company.company_name
    row = BillingPayment(
        company_id=company.id,
        user_id=user.id,
        plan_name=quote["plan_name"],
        amount_inr=quote["amount_inr"],
        payment_method="UPI",
        reference_note=None,
        payment_date=now,
        status=STATUS_PENDING,
        module_key=quote["module_key"],
        module_label=quote["module_label"],
        plan_type=quote["plan_type"],
        billing_period=quote["billing_period"],
        subscription_duration=quote["subscription_duration"],
        currency="INR",
        pricing_snapshot={
            "module": quote["module_label"],
            "module_key": quote["module_key"],
            "plan": quote["plan_name"],
            "plan_type": quote["plan_type"],
            "catalog_id": quote["catalog_id"],
            "billing_period": quote["billing_period"],
            "billing_period_label": quote["billing_period_label"],
            "subscription_duration": quote["subscription_duration"],
            "monthly_price": quote["monthly_price"],
            "original_plan_price": quote["monthly_price"],
            "amount_inr": quote["amount_inr"],
            "currency": "INR",
        },
        payment_submitted_at=now,
        customer_name_snapshot=customer_name,
        company_name_snapshot=company.company_name,
        email_snapshot=user.email,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        again = _find_pending(
            db,
            company_id=company.id,
            module_key=quote["module_key"],
            plan_type=quote["plan_type"],
            billing_period=quote["billing_period"],
        )
        if again:
            return again, True
        raise
    row.payment_code = payment_code_for(row.id)
    row.reference_note = row.payment_code
    _notify_admins(db, row, user, company)
    db.flush()
    return row, False


def verify_payment(db: Session, *, admin: PlatformAdmin, payment_id: int) -> BillingPayment:
    row = get_billing_payment(db, payment_id)
    st = row.status if row.status != "pending" else STATUS_PENDING
    if st == STATUS_VERIFIED:
        return row
    if st != STATUS_PENDING:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only pending payments can be verified")
    now = _utc_now()
    row.status = STATUS_VERIFIED
    row.verified_by_admin_id = admin.id
    row.verified_at = now
    row.updated_at = now
    db.add(row)
    db.flush()
    return row


def reject_payment(
    db: Session,
    *,
    admin: PlatformAdmin,
    payment_id: int,
    reason: str,
    note: str | None = None,
) -> BillingPayment:
    row = get_billing_payment(db, payment_id)
    st = row.status if row.status != "pending" else STATUS_PENDING
    if st != STATUS_PENDING:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only pending payments can be rejected")
    key = (reason or "").strip().lower()
    if key not in REJECT_REASONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid rejection reason")
    extra = (note or "").strip()
    if key == "other" and len(extra) < 3:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Please describe the rejection reason")
    now = _utc_now()
    row.status = STATUS_REJECTED
    row.rejected_by_admin_id = admin.id
    row.rejected_at = now
    row.rejection_reason = key
    row.rejection_note = extra or None
    row.updated_at = now
    db.add(row)
    db.flush()
    return row


def list_admin_notifications(db: Session, *, unread_only: bool = False, limit: int = 50) -> list[AdminNotification]:
    q = select(AdminNotification)
    if unread_only:
        q = q.where(AdminNotification.is_read == 0)
    q = q.order_by(AdminNotification.created_at.desc()).limit(limit)
    return list(db.execute(q).scalars().all())


def mark_notification_read(db: Session, notification_id: int) -> AdminNotification:
    row = db.get(AdminNotification, notification_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    row.is_read = 1
    db.add(row)
    db.flush()
    return row
