"""Read-only listing of SaaS billing payment records for Platform Admin.

Does not verify, reject, generate invoices, or change subscriptions.
Desktop license payments stay in desktop_payments / /admin/desktop-payments.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import BillingPayment, Company, CompanyUser

STATUS_PENDING = "pending"
STATUS_VERIFIED = "verified"
STATUS_REJECTED = "rejected"
ALLOWED_STATUSES = {STATUS_PENDING, STATUS_VERIFIED, STATUS_REJECTED}


def _primary_user(company: Company | None) -> CompanyUser | None:
    if not company or not company.users:
        return None
    return sorted(company.users, key=lambda u: u.id)[0]


def serialize_billing_payment(row: BillingPayment) -> dict[str, Any]:
    company = row.company
    user = row.user or _primary_user(company)
    return {
        "id": row.id,
        "company_id": row.company_id,
        "user_id": row.user_id,
        "customer_name": (user.name if user and user.name else None) or (company.company_name if company else None),
        "company_name": company.company_name if company else None,
        "email": user.email if user else None,
        "phone": None,
        "subscription_plan": row.plan_name,
        "subscription_start": company.subscription_start.isoformat() if company and company.subscription_start else None,
        "subscription_end": company.subscription_end.isoformat() if company and company.subscription_end else None,
        "amount_inr": row.amount_inr,
        "payment_method": row.payment_method,
        "reference_note": row.reference_note,
        "payment_date": row.payment_date.isoformat() if row.payment_date else None,
        "status": row.status,
        "has_proof": bool(row.proof_path),
    }


def billing_payment_counts(db: Session) -> dict[str, int]:
    rows = db.execute(select(BillingPayment.status, func.count(BillingPayment.id)).group_by(BillingPayment.status)).all()
    counts = {STATUS_PENDING: 0, STATUS_VERIFIED: 0, STATUS_REJECTED: 0}
    for status_val, n in rows:
        if status_val in counts:
            counts[status_val] = int(n)
    return counts


def list_billing_payments(db: Session, *, status_filter: str | None = None, limit: int = 500) -> list[BillingPayment]:
    q = select(BillingPayment).options(
        selectinload(BillingPayment.company).selectinload(Company.users),
        selectinload(BillingPayment.user),
    )
    if status_filter:
        if status_filter not in ALLOWED_STATUSES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payment status")
        q = q.where(BillingPayment.status == status_filter)
    q = q.order_by(BillingPayment.payment_date.desc(), BillingPayment.id.desc()).limit(limit)
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
