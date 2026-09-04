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
    """Generate a new key and durable storage fields (hash + optional ciphertext)."""
    plaintext = generate_license_key(prefix=prefix)
    normalized = normalize_license_key(plaintext)
    parts = normalized.split("-")
    key_prefix = parts[0] if parts else prefix
    key_last4 = parts[-1][-4:] if parts else normalized[-4:]
    secret = getattr(settings, "license_key_encryption_secret", None)
    encrypted = encrypt_license_key(plaintext, secret)
    return LicenseKeyMaterial(
        plaintext=plaintext,
        key_hash=hash_license_key(plaintext),
        key_encrypted=encrypted,
        key_prefix=key_prefix,
        key_last4=key_last4,
    )


def list_active_products_with_plans(db: Session) -> list[DesktopProduct]:
    """Catalog foundation: active products with active plans, sorted."""
    q = (
        select(DesktopProduct)
        .where(DesktopProduct.listing_active == 1)
        .options(selectinload(DesktopProduct.plans))
        .order_by(DesktopProduct.sort_order.asc(), DesktopProduct.id.asc())
    )
    products = list(db.execute(q).scalars().all())
    for p in products:
        p.plans = sorted(
            [pl for pl in (p.plans or []) if pl.listing_active == 1],
            key=lambda pl: (pl.sort_order, pl.id),
        )
    return products


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
