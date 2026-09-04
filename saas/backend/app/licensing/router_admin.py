"""Admin catalog/pricing routes for desktop licensing (Phase 2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import Settings, get_settings
from app.deps import get_db_session, get_platform_admin
from app.licensing.feature_flag import require_desktop_licensing_enabled
from app.licensing.models import DesktopProduct
from app.licensing.schemas import (
    DesktopPlanCreate,
    DesktopPlanOut,
    DesktopPlanPatch,
    DesktopProductPatch,
    DesktopProductWithPlansOut,
    LicensingHealthOut,
)
from app.licensing.service import (
    create_desktop_plan,
    foundation_health,
    get_plan_or_404,
    get_product_or_404,
    list_all_products_with_plans,
    patch_desktop_plan,
    patch_desktop_product,
    serialize_product,
)
from app.models import PlatformAdmin

router = APIRouter(prefix="/api/admin/desktop", tags=["admin-desktop-licensing"])


def _plan_out(plan) -> dict:
    return {
        "id": plan.id,
        "product_id": plan.product_id,
        "code": plan.code,
        "name": plan.name,
        "description": plan.description,
        "price_inr": plan.price_inr,
        "duration_days": plan.duration_days,
        "seats": plan.seats,
        "listing_active": bool(plan.listing_active),
        "sort_order": plan.sort_order,
    }


def _reload_product(db: Session, product_id: int) -> DesktopProduct:
    q = (
        select(DesktopProduct)
        .where(DesktopProduct.id == product_id)
        .options(selectinload(DesktopProduct.plans))
    )
    row = db.execute(q).scalar_one()
    row.plans = sorted(list(row.plans or []), key=lambda pl: (pl.sort_order, pl.id))
    return row


@router.get("/health", response_model=LicensingHealthOut)
def admin_desktop_licensing_health(
    _: None = Depends(require_desktop_licensing_enabled),
    admin: PlatformAdmin = Depends(get_platform_admin),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    del admin
    out = foundation_health(db, enabled=bool(settings.enable_desktop_licensing))
    out["phase"] = "2-admin-catalog"
    return out


@router.get("/products", response_model=list[DesktopProductWithPlansOut])
def admin_list_desktop_products(
    _: None = Depends(require_desktop_licensing_enabled),
    admin: PlatformAdmin = Depends(get_platform_admin),
    db: Session = Depends(get_db_session),
):
    """Admin catalog including inactive products/plans."""
    del admin
    products = list_all_products_with_plans(db)
    return [serialize_product(p) for p in products]


@router.patch("/products/{product_id}", response_model=DesktopProductWithPlansOut)
def admin_patch_desktop_product(
    product_id: int,
    body: DesktopProductPatch,
    _: None = Depends(require_desktop_licensing_enabled),
    admin: PlatformAdmin = Depends(get_platform_admin),
    db: Session = Depends(get_db_session),
):
    del admin
    product = get_product_or_404(db, product_id)
    patch_desktop_product(db, product, body.model_dump(exclude_unset=True))
    db.commit()
    return serialize_product(_reload_product(db, product_id))


@router.post("/products/{product_id}/plans", response_model=DesktopPlanOut, status_code=201)
def admin_create_desktop_plan(
    product_id: int,
    body: DesktopPlanCreate,
    _: None = Depends(require_desktop_licensing_enabled),
    admin: PlatformAdmin = Depends(get_platform_admin),
    db: Session = Depends(get_db_session),
):
    del admin
    plan = create_desktop_plan(
        db,
        product_id=product_id,
        code=body.code,
        name=body.name,
        description=body.description,
        price_inr=body.price_inr,
        duration_days=body.duration_days,
        listing_active=body.listing_active,
        sort_order=body.sort_order,
    )
    db.commit()
    db.refresh(plan)
    return _plan_out(plan)


@router.patch("/plans/{plan_id}", response_model=DesktopPlanOut)
def admin_patch_desktop_plan(
    plan_id: int,
    body: DesktopPlanPatch,
    _: None = Depends(require_desktop_licensing_enabled),
    admin: PlatformAdmin = Depends(get_platform_admin),
    db: Session = Depends(get_db_session),
):
    del admin
    plan = get_plan_or_404(db, plan_id)
    patch_desktop_plan(db, plan, body.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(plan)
    return _plan_out(plan)
