"""Desktop licensing service foundation (Phase 1).

Later phases add orders, payment approval, minting emails, downloads, and
Ed25519 machine entitlement signing. This module owns catalog reads, secure
key material helpers, transactional license row creation, and audit events.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload
from fastapi import HTTPException

from app.config import Settings
from app.licensing.constants import (
    DESKTOP_PRODUCT_CODES,
    ENTITLEMENT_PAID,
    LICENSE_STATUS_ISSUED,
    PHASE_FOUNDATION,
)
from app.licensing.keys import (
    encrypt_license_key,
    generate_license_key,
    hash_license_key,
    mask_license_key,
    normalize_license_key,
    require_valid_encryption_secret,
)
from app.licensing.models import (
    DesktopLicense,
    DesktopLicenseEvent,
    DesktopPlan,
    DesktopProduct,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LicenseKeyMaterial:
    plaintext: str
    key_hash: str
    key_encrypted: Optional[str]
    key_prefix: str
    key_last4: str

    @property
    def key_masked(self) -> str:
        return mask_license_key(self.plaintext)


def mint_license_key_material(
    settings: Settings,
    *,
    prefix: str = "AQ",
) -> LicenseKeyMaterial:
    """Generate a new key with hash + Fernet ciphertext (required for reveal/email).

    Fail-closed: LICENSE_KEY_ENCRYPTION_SECRET must be a valid Fernet key.
    Hash-only minting is not allowed — plaintext cannot be recovered later.
    """
    secret = require_valid_encryption_secret(
        getattr(settings, "license_key_encryption_secret", None)
    )
    plaintext = generate_license_key(prefix=prefix)
    normalized = normalize_license_key(plaintext)
    parts = normalized.split("-")
    key_prefix = parts[0] if parts else prefix
    key_last4 = parts[-1][-4:] if parts else normalized[-4:]
    encrypted = encrypt_license_key(plaintext, secret)
    return LicenseKeyMaterial(
        plaintext=plaintext,
        key_hash=hash_license_key(plaintext),
        key_encrypted=encrypted,
        key_prefix=key_prefix,
        key_last4=key_last4,
    )


def list_active_products_with_plans(db: Session) -> list[DesktopProduct]:
    """Customer catalog: active products with active plans only."""
    return _list_products_with_plans(db, include_inactive=False)


def list_all_products_with_plans(db: Session) -> list[DesktopProduct]:
    """Admin catalog: all products and plans (including inactive)."""
    return _list_products_with_plans(db, include_inactive=True)


def _list_products_with_plans(db: Session, *, include_inactive: bool) -> list[DesktopProduct]:
    q = (
        select(DesktopProduct)
        .options(selectinload(DesktopProduct.plans))
        .order_by(DesktopProduct.sort_order.asc(), DesktopProduct.id.asc())
    )
    if not include_inactive:
        q = q.where(DesktopProduct.listing_active == 1)
    products = list(db.execute(q).scalars().all())
    for p in products:
        plans = list(p.plans or [])
        if not include_inactive:
            plans = [pl for pl in plans if pl.listing_active == 1]
        p.plans = sorted(plans, key=lambda pl: (pl.sort_order, pl.id))
    return products


def get_product_or_404(db: Session, product_id: int) -> DesktopProduct:
    product = db.get(DesktopProduct, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Desktop product not found")
    return product


def get_plan_or_404(db: Session, plan_id: int) -> DesktopPlan:
    plan = db.get(DesktopPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Desktop plan not found")
    return plan


def patch_desktop_product(
    db: Session,
    product: DesktopProduct,
    patch: dict,
) -> DesktopProduct:
    """Admin partial update for a desktop product (catalog/pricing Phase 2)."""
    if "name" in patch:
        name = (patch["name"] or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="name cannot be empty")
        product.name = name
    if "description" in patch:
        desc = patch["description"]
        product.description = (desc.strip() or None) if isinstance(desc, str) else desc
    if "listing_active" in patch and patch["listing_active"] is not None:
        product.listing_active = 1 if patch["listing_active"] else 0
    if "sort_order" in patch and patch["sort_order"] is not None:
        product.sort_order = int(patch["sort_order"])
    if "buy_url_path" in patch:
        buy = patch["buy_url_path"]
        product.buy_url_path = (buy.strip() or None) if isinstance(buy, str) else buy
    db.add(product)
    db.flush()
    return product


def create_desktop_plan(
    db: Session,
    *,
    product_id: int,
    code: str,
    name: str,
    description: str | None,
    price_inr: int,
    duration_days: int = 365,
    listing_active: bool = True,
    sort_order: int = 10,
) -> DesktopPlan:
    """Create a per-seat plan. seats is always 1 (no shared / max_devices plans)."""
    get_product_or_404(db, product_id)
    code = (code or "").strip().upper()
    name = (name or "").strip()
    if not code or not name:
        raise HTTPException(status_code=400, detail="code and name are required")
    if price_inr < 0:
        raise HTTPException(status_code=400, detail="price_inr must be >= 0")
    if duration_days < 1:
        raise HTTPException(status_code=400, detail="duration_days must be >= 1")
    existing = db.execute(
        select(DesktopPlan).where(DesktopPlan.product_id == product_id, DesktopPlan.code == code)
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail=f"Plan code '{code}' already exists for this product")
    plan = DesktopPlan(
        product_id=product_id,
        code=code,
        name=name,
        description=(description or "").strip() or None,
        price_inr=int(price_inr),
        duration_days=int(duration_days),
        seats=1,
        listing_active=1 if listing_active else 0,
        sort_order=int(sort_order),
    )
    db.add(plan)
    db.flush()
    return plan


def patch_desktop_plan(db: Session, plan: DesktopPlan, patch: dict) -> DesktopPlan:
    """Admin partial update. seats remain 1 — shared-seat / max_devices not allowed."""
    if "code" in patch and patch["code"] is not None:
        new_code = str(patch["code"]).strip().upper()
        if not new_code:
            raise HTTPException(status_code=400, detail="code cannot be empty")
        clash = db.execute(
            select(DesktopPlan).where(
                DesktopPlan.product_id == plan.product_id,
                DesktopPlan.code == new_code,
                DesktopPlan.id != plan.id,
            )
        ).scalar_one_or_none()
        if clash:
            raise HTTPException(status_code=409, detail=f"Plan code '{new_code}' already exists for this product")
        plan.code = new_code
    if "name" in patch and patch["name"] is not None:
        name = str(patch["name"]).strip()
        if not name:
            raise HTTPException(status_code=400, detail="name cannot be empty")
        plan.name = name
    if "description" in patch:
        desc = patch["description"]
        plan.description = (desc.strip() or None) if isinstance(desc, str) else desc
    if "price_inr" in patch and patch["price_inr"] is not None:
        if int(patch["price_inr"]) < 0:
            raise HTTPException(status_code=400, detail="price_inr must be >= 0")
        plan.price_inr = int(patch["price_inr"])
    if "duration_days" in patch and patch["duration_days"] is not None:
        if int(patch["duration_days"]) < 1:
            raise HTTPException(status_code=400, detail="duration_days must be >= 1")
        plan.duration_days = int(patch["duration_days"])
    if "listing_active" in patch and patch["listing_active"] is not None:
        plan.listing_active = 1 if patch["listing_active"] else 0
    if "sort_order" in patch and patch["sort_order"] is not None:
        plan.sort_order = int(patch["sort_order"])
    plan.seats = 1
    db.add(plan)
    db.flush()
    return plan


def count_seeded_catalog(db: Session) -> tuple[int, int]:
    products = db.execute(select(func.count()).select_from(DesktopProduct)).scalar_one()
    plans = db.execute(select(func.count()).select_from(DesktopPlan)).scalar_one()
    return int(products or 0), int(plans or 0)


def foundation_health(db: Session, *, enabled: bool) -> dict[str, Any]:
    products, plans = count_seeded_catalog(db)
    return {
        "enabled": enabled,
        "products_seeded": products,
        "plans_seeded": plans,
        "phase": PHASE_FOUNDATION,
        "message": (
            "Desktop licensing foundation is available."
            if enabled
            else "Desktop licensing is disabled (ENABLE_DESKTOP_LICENSING=false)."
        ),
    }


def record_license_event(
    db: Session,
    *,
    license_id: Optional[int],
    actor_type: str,
    actor_id: Optional[int],
    event_type: str,
    meta: Optional[dict[str, Any]] = None,
) -> DesktopLicenseEvent:
    event = DesktopLicenseEvent(
        license_id=license_id,
        actor_type=actor_type,
        actor_id=actor_id,
        event_type=event_type,
        meta_json=json.dumps(meta, default=str) if meta else None,
    )
    db.add(event)
    return event


def create_paid_license_row(
    db: Session,
    settings: Settings,
    *,
    product_id: int,
    plan_id: Optional[int],
    order_id: Optional[int],
    company_id: int,
    licensed_user_id: int,
    seat_index: Optional[int],
    duration_days: int,
    created_by_admin_id: Optional[int] = None,
    key_prefix_code: str = "AQ",
) -> tuple[DesktopLicense, str]:
    """
    Transactional helper: mint one independent paid license seat.

    Returns (license_row, plaintext_key). Caller must commit and deliver plaintext
    once (email / reveal). Does not log plaintext.
    """
    material = mint_license_key_material(settings, prefix=key_prefix_code)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=int(duration_days)) if duration_days > 0 else None
    row = DesktopLicense(
        product_id=product_id,
        plan_id=plan_id,
        order_id=order_id,
        company_id=company_id,
        licensed_user_id=licensed_user_id,
        entitlement_type=ENTITLEMENT_PAID,
        seat_index=seat_index,
        key_prefix=material.key_prefix,
        key_last4=material.key_last4,
        key_hash=material.key_hash,
        key_encrypted=material.key_encrypted,
        status=LICENSE_STATUS_ISSUED,
        issued_at=now,
        expires_at=expires_at,
        created_by_admin_id=created_by_admin_id,
    )
    db.add(row)
    db.flush()
    record_license_event(
        db,
        license_id=row.id,
        actor_type="system" if created_by_admin_id is None else "admin",
        actor_id=created_by_admin_id,
        event_type="license_issued",
        meta={
            "entitlement_type": ENTITLEMENT_PAID,
            "seat_index": seat_index,
            "product_id": product_id,
            "order_id": order_id,
        },
    )
    return row, material.plaintext


def create_paid_licenses_for_seats(
    db: Session,
    settings: Settings,
    *,
    product_id: int,
    plan_id: int,
    order_id: int,
    company_id: int,
    licensed_user_id: int,
    seat_count: int,
    duration_days: int,
    created_by_admin_id: Optional[int] = None,
) -> list[tuple[DesktopLicense, str]]:
    """Mint N independent keys (one per seat). Call inside a DB transaction."""
    if seat_count < 1:
        raise ValueError("seat_count must be >= 1")
    minted: list[tuple[DesktopLicense, str]] = []
    for i in range(1, seat_count + 1):
        minted.append(
            create_paid_license_row(
                db,
                settings,
                product_id=product_id,
                plan_id=plan_id,
                order_id=order_id,
                company_id=company_id,
                licensed_user_id=licensed_user_id,
                seat_index=i,
                duration_days=duration_days,
                created_by_admin_id=created_by_admin_id,
            )
        )
    return minted


def product_code_is_known(code: str) -> bool:
    return (code or "").strip().upper() in DESKTOP_PRODUCT_CODES


def serialize_product(product: DesktopProduct) -> dict[str, Any]:
    return {
        "id": product.id,
        "code": product.code,
        "name": product.name,
        "description": product.description,
        "listing_active": bool(product.listing_active),
        "trial_enabled": bool(product.trial_enabled),
        "trial_duration_days": int(product.trial_duration_days or 7),
        "sort_order": product.sort_order,
        "buy_url_path": product.buy_url_path,
        "plans": [
            {
                "id": pl.id,
                "product_id": pl.product_id,
                "code": pl.code,
                "name": pl.name,
                "description": pl.description,
                "price_inr": pl.price_inr,
                "duration_days": pl.duration_days,
                "seats": pl.seats,
                "listing_active": bool(pl.listing_active),
                "sort_order": pl.sort_order,
            }
            for pl in (product.plans or [])
        ],
    }


def expected_seed_product_codes() -> Sequence[str]:
    return DESKTOP_PRODUCT_CODES
