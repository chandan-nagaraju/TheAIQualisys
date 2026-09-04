"""Customer desktop licensing routes (catalog, orders, Phase 4 payments)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.deps import get_company_for_user, get_current_company_user, get_db_session
from app.licensing.feature_flag import require_desktop_licensing_enabled
from app.licensing.orders import (
    create_desktop_order,
    get_customer_order,
    list_customer_orders,
    serialize_order,
)
from app.licensing.schemas import (
    DesktopCheckoutContextOut,
    DesktopOrderCreate,
    DesktopOrderOut,
    DesktopPaymentOut,
    DesktopProductWithPlansOut,
    DesktopUpiSettingsOut,
    LicensingHealthOut,
)
from app.licensing.service import foundation_health, list_active_products_with_plans, serialize_product
from app.models import CompanyUser

router = APIRouter(prefix="/api/desktop", tags=["desktop-licensing"])


@router.get("/health", response_model=LicensingHealthOut)
def customer_desktop_licensing_health(
    _: None = Depends(require_desktop_licensing_enabled),
    user: CompanyUser = Depends(get_current_company_user),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    del user
    out = foundation_health(db, enabled=bool(settings.enable_desktop_licensing))
    out["phase"] = "4-payment-mint"
    return out


@router.get("/products", response_model=list[DesktopProductWithPlansOut])
def customer_list_desktop_products(
    _: None = Depends(require_desktop_licensing_enabled),
    user: CompanyUser = Depends(get_current_company_user),
    db: Session = Depends(get_db_session),
):
    del user
    products = list_active_products_with_plans(db)
    return [serialize_product(p) for p in products]


@router.get("/checkout-context", response_model=DesktopCheckoutContextOut)
def customer_checkout_context(
    _: None = Depends(require_desktop_licensing_enabled),
    user: CompanyUser = Depends(get_current_company_user),
    db: Session = Depends(get_db_session),
):
    company = get_company_for_user(user, db)
    return DesktopCheckoutContextOut(
        user_id=user.id,
        email=user.email,
        company_id=company.id,
        company_name=company.company_name,
    )


@router.post("/orders", response_model=DesktopOrderOut, status_code=201)
def customer_create_order(
    body: DesktopOrderCreate,
    _: None = Depends(require_desktop_licensing_enabled),
    user: CompanyUser = Depends(get_current_company_user),
    db: Session = Depends(get_db_session),
):
    company = get_company_for_user(user, db)
    try:
        order = create_desktop_order(
            db,
            user=user,
            company=company,
            product_id=body.product_id,
            plan_id=body.plan_id,
            seats=body.seats,
        )
        db.commit()
        db.refresh(order)
    except Exception:
        db.rollback()
        raise
    return serialize_order(order)


@router.get("/orders", response_model=list[DesktopOrderOut])
def customer_list_orders(
    _: None = Depends(require_desktop_licensing_enabled),
    user: CompanyUser = Depends(get_current_company_user),
    db: Session = Depends(get_db_session),
):
    return [serialize_order(o) for o in list_customer_orders(db, user=user)]


@router.get("/orders/{order_id}", response_model=DesktopOrderOut)
def customer_get_order(
    order_id: int,
    _: None = Depends(require_desktop_licensing_enabled),
    user: CompanyUser = Depends(get_current_company_user),
    db: Session = Depends(get_db_session),
):
    order = get_customer_order(db, user=user, order_id=order_id)
    return serialize_order(order)


@router.get("/upi-settings", response_model=DesktopUpiSettingsOut)
def customer_upi_settings(
    _: None = Depends(require_desktop_licensing_enabled),
    user: CompanyUser = Depends(get_current_company_user),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    del user
    from app.licensing.payments import get_or_create_upi_settings, serialize_upi_settings

    row = get_or_create_upi_settings(db, settings)
    db.commit()
    return serialize_upi_settings(row)


@router.get("/orders/{order_id}/payments", response_model=list[DesktopPaymentOut])
def customer_list_order_payments(
    order_id: int,
    _: None = Depends(require_desktop_licensing_enabled),
    user: CompanyUser = Depends(get_current_company_user),
    db: Session = Depends(get_db_session),
):
    from app.licensing.payments import list_customer_payments_for_order, serialize_payment

    return [serialize_payment(p) for p in list_customer_payments_for_order(db, user=user, order_id=order_id)]


@router.post("/orders/{order_id}/payments", response_model=DesktopPaymentOut, status_code=201)
async def customer_submit_payment(
    order_id: int,
    _: None = Depends(require_desktop_licensing_enabled),
    user: CompanyUser = Depends(get_current_company_user),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    utr_reference: str = Form(...),
    screenshot: UploadFile | None = File(None),
):
    """Submit UTR (+ optional screenshot). Does not mark payment successful."""
    from app.licensing.payments import save_payment_screenshot, serialize_payment, submit_payment_for_order

    # Ownership check before accepting upload
    get_customer_order(db, user=user, order_id=order_id)
    shot_path = None
    shot_mime = None
    if screenshot is not None and screenshot.filename:
        shot_path, shot_mime = await save_payment_screenshot(
            upload_root=Path(settings.workspace_upload_dir),
            company_id=user.company_id,
            order_id=order_id,
            file=screenshot,
        )
    try:
        payment = submit_payment_for_order(
            db,
            settings,
            user=user,
            order_id=order_id,
            utr_reference=utr_reference,
            screenshot_path=shot_path,
            screenshot_mime=shot_mime,
        )
        db.commit()
        db.refresh(payment)
    except Exception:
        db.rollback()
        raise
    return serialize_payment(payment)
