"""Customer desktop order creation (Phase 3).

Creates pending_payment orders with price snapshots and TAQ-YYYY-###### numbers.
Does NOT mint licenses, accept payment, or bind devices.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.licensing.constants import ORDER_STATUS_PENDING_PAYMENT
from app.licensing.models import DesktopOrder, DesktopPlan, DesktopProduct
from app.models import Company, CompanyUser

_ORDER_TZ = ZoneInfo("Asia/Kolkata")


def order_year_now(*, when: datetime | None = None) -> int:
    """Calendar year used in TAQ-YYYY-###### (Asia/Kolkata)."""
    dt = when or datetime.now(_ORDER_TZ)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_ORDER_TZ)
    else:
        dt = dt.astimezone(_ORDER_TZ)
    return int(dt.year)


def format_order_number(year: int, seq: int) -> str:
    if seq < 1 or seq > 999_999:
        raise ValueError("order sequence out of range for TAQ-YYYY-######")
    return f"TAQ-{int(year):04d}-{int(seq):06d}"


def allocate_order_number(db: Session, *, year: int | None = None) -> str:
    """
    Atomically allocate the next TAQ-YYYY-###### within a DB transaction.
    Uses desktop_order_number_counters with INSERT … ON CONFLICT DO UPDATE.
    """
    y = int(year if year is not None else order_year_now())
    row = db.execute(
        text(
            """
            INSERT INTO desktop_order_number_counters (year, last_value)
            VALUES (:year, 1)
            ON CONFLICT (year) DO UPDATE
              SET last_value = desktop_order_number_counters.last_value + 1
            RETURNING last_value
            """
        ),
        {"year": y},
    ).one()
    seq = int(row[0])
    return format_order_number(y, seq)


def compute_order_total(*, unit_price_inr: int, seats: int) -> int:
    if seats < 1:
        raise HTTPException(status_code=400, detail="seats must be >= 1")
    if unit_price_inr < 0:
        raise HTTPException(status_code=400, detail="unit_price_inr must be >= 0")
    return int(unit_price_inr) * int(seats)


def create_desktop_order(
    db: Session,
    *,
    user: CompanyUser,
    company: Company,
    product_id: int,
    plan_id: int,
    seats: int,
) -> DesktopOrder:
    """
    Transactional order create:
    - validates active product + active plan belonging to product
    - snapshots unit price and catalog labels
    - allocates unique order_number
    - status = pending_payment
    Caller must commit.
    """
    if seats < 1:
        raise HTTPException(status_code=400, detail="seats must be >= 1")
    if int(company.id) != int(user.company_id):
        raise HTTPException(status_code=400, detail="Company mismatch")

    product = db.get(DesktopProduct, product_id)
    if not product or int(product.listing_active) != 1:
        raise HTTPException(status_code=404, detail="Product not found or not available")

    plan = db.get(DesktopPlan, plan_id)
    if not plan or int(plan.listing_active) != 1:
        raise HTTPException(status_code=404, detail="Plan not found or not available")
    if int(plan.product_id) != int(product.id):
        raise HTTPException(status_code=400, detail="Plan does not belong to the selected product")

    unit = int(plan.price_inr)
    total = compute_order_total(unit_price_inr=unit, seats=seats)
    order_number = allocate_order_number(db)

    order = DesktopOrder(
        order_number=order_number,
        company_id=int(company.id),
        user_id=int(user.id),
        product_id=int(product.id),
        plan_id=int(plan.id),
        product_code=product.code,
        product_name=product.name,
        plan_code=plan.code,
        plan_name=plan.name,
        duration_days=int(plan.duration_days),
        seats=int(seats),
        unit_price_inr=unit,
        total_price_inr=total,
        currency="INR",
        status=ORDER_STATUS_PENDING_PAYMENT,
    )
    db.add(order)
    db.flush()
    return order


def get_customer_order(
    db: Session,
    *,
    user: CompanyUser,
    order_id: int | None = None,
    order_number: str | None = None,
) -> DesktopOrder:
    q = select(DesktopOrder).where(DesktopOrder.user_id == int(user.id))
    if order_id is not None:
        q = q.where(DesktopOrder.id == int(order_id))
    elif order_number:
        q = q.where(DesktopOrder.order_number == order_number.strip().upper())
    else:
        raise HTTPException(status_code=400, detail="order_id or order_number required")
    order = db.execute(q).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


def list_customer_orders(db: Session, *, user: CompanyUser) -> list[DesktopOrder]:
    return list(
        db.execute(
            select(DesktopOrder)
            .where(DesktopOrder.user_id == int(user.id))
            .order_by(DesktopOrder.id.desc())
        )
        .scalars()
        .all()
    )


def list_all_orders_admin(db: Session, *, limit: int = 200) -> list[DesktopOrder]:
    """Admin read-only list (no payment actions in Phase 3)."""
    lim = max(1, min(int(limit), 500))
    return list(
        db.execute(select(DesktopOrder).order_by(DesktopOrder.id.desc()).limit(lim)).scalars().all()
    )


def serialize_order(order: DesktopOrder) -> dict:
    return {
        "id": order.id,
        "order_number": order.order_number,
        "company_id": order.company_id,
        "user_id": order.user_id,
        "product_id": order.product_id,
        "plan_id": order.plan_id,
        "product_code": order.product_code,
        "product_name": order.product_name,
        "plan_code": order.plan_code,
        "plan_name": order.plan_name,
        "duration_days": order.duration_days,
        "seats": order.seats,
        "unit_price_inr": order.unit_price_inr,
        "total_price_inr": order.total_price_inr,
        "currency": order.currency,
        "status": order.status,
        "created_at": order.created_at.isoformat() if order.created_at else None,
    }
