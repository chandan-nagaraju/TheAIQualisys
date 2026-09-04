"""Admin foundation routes for desktop licensing (Phase 1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.deps import get_db_session, get_platform_admin
from app.licensing.feature_flag import require_desktop_licensing_enabled
from app.licensing.schemas import DesktopProductWithPlansOut, LicensingHealthOut
from app.licensing.service import foundation_health, list_active_products_with_plans, serialize_product
from app.models import PlatformAdmin

router = APIRouter(prefix="/api/admin/desktop", tags=["admin-desktop-licensing"])


@router.get("/health", response_model=LicensingHealthOut)
def admin_desktop_licensing_health(
    _: None = Depends(require_desktop_licensing_enabled),
    admin: PlatformAdmin = Depends(get_platform_admin),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    del admin  # auth gate only
    return foundation_health(db, enabled=bool(settings.enable_desktop_licensing))


@router.get("/products", response_model=list[DesktopProductWithPlansOut])
def admin_list_desktop_products(
    _: None = Depends(require_desktop_licensing_enabled),
    admin: PlatformAdmin = Depends(get_platform_admin),
    db: Session = Depends(get_db_session),
):
    del admin
    products = list_active_products_with_plans(db)
    return [serialize_product(p) for p in products]
