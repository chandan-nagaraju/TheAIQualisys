"""Admin catalog/pricing routes for desktop licensing (Phase 2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import Settings, get_settings
from app.deps import get_db_session, get_platform_admin
from app.licensing.feature_flag import require_desktop_licensing_enabled
from app.licensing.models import DesktopProduct
from app.licensing.orders import list_all_orders_admin, serialize_order
from app.licensing.schemas import (
    DesktopLicenseEmailDeliveryOut,
    DesktopLicenseOut,
    DesktopLicenseRevealOut,
    DesktopOrderOut,
    DesktopPaymentApproveOut,
    DesktopPaymentOut,
    DesktopPaymentRejectBody,
    DesktopPlanCreate,
    DesktopPlanOut,
    DesktopPlanPatch,
    DesktopProductPatch,
    DesktopProductWithPlansOut,
    DesktopUpiSettingsAdminOut,
    DesktopUpiSettingsPatch,
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
    out["phase"] = "5-email-licenses"
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


@router.get("/orders", response_model=list[DesktopOrderOut])
def admin_list_desktop_orders(
    _: None = Depends(require_desktop_licensing_enabled),
    admin: PlatformAdmin = Depends(get_platform_admin),
    db: Session = Depends(get_db_session),
    limit: int = 200,
):
    """Order list for ops visibility."""
    del admin
    return [serialize_order(o) for o in list_all_orders_admin(db, limit=limit)]


@router.get("/upi-settings", response_model=DesktopUpiSettingsAdminOut)
def admin_get_upi_settings(
    _: None = Depends(require_desktop_licensing_enabled),
    admin: PlatformAdmin = Depends(get_platform_admin),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    del admin
    from app.licensing.payments import get_or_create_upi_settings, serialize_upi_settings

    row = get_or_create_upi_settings(db, settings)
    db.commit()
    return serialize_upi_settings(row, include_admin=True)


@router.put("/upi-settings", response_model=DesktopUpiSettingsAdminOut)
def admin_put_upi_settings(
    body: DesktopUpiSettingsPatch,
    _: None = Depends(require_desktop_licensing_enabled),
    admin: PlatformAdmin = Depends(get_platform_admin),
    db: Session = Depends(get_db_session),
):
    from app.licensing.payments import serialize_upi_settings, update_upi_settings

    row = update_upi_settings(
        db,
        admin=admin,
        upi_id=body.upi_id,
        payee_name=body.payee_name,
        instructions=body.instructions,
        clear_qr=body.clear_qr,
    )
    db.commit()
    db.refresh(row)
    return serialize_upi_settings(row, include_admin=True)


@router.get("/payment-requests", response_model=list[dict])
def admin_list_payment_requests(
    _: None = Depends(require_desktop_licensing_enabled),
    admin: PlatformAdmin = Depends(get_platform_admin),
    db: Session = Depends(get_db_session),
    status: str | None = "pending_review",
    limit: int = 200,
):
    del admin
    from app.licensing.orders import serialize_order
    from app.licensing.payments import list_payment_requests, serialize_payment

    rows = list_payment_requests(db, status=status or None, limit=limit)
    out = []
    for p in rows:
        item = serialize_payment(p)
        item["order"] = serialize_order(p.order) if p.order else None
        out.append(item)
    return out


@router.post("/payment-requests/{payment_id}/approve", response_model=DesktopPaymentApproveOut)
def admin_approve_payment(
    payment_id: int,
    _: None = Depends(require_desktop_licensing_enabled),
    admin: PlatformAdmin = Depends(get_platform_admin),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    from app.licensing.customer_licenses import (
        attempt_send_license_email_for_order,
        serialize_email_delivery,
    )
    from app.licensing.orders import serialize_order
    from app.licensing.payments import approve_payment_and_mint_licenses, serialize_payment

    try:
        payment, order, licenses = approve_payment_and_mint_licenses(
            db, settings, admin=admin, payment_id=payment_id
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    # Email is separate from mint: failure must not roll back licenses.
    email_out = None
    try:
        delivery = attempt_send_license_email_for_order(
            db,
            settings,
            order_id=order.id,
            actor_type="admin",
            actor_id=admin.id,
            is_resend=False,
            enforce_rate_limit=False,
        )
        db.commit()
        email_out = serialize_email_delivery(delivery)
    except Exception:
        db.rollback()
        # Soft-fail email; licenses already committed
        email_out = None

    return {
        "payment": serialize_payment(payment),
        "order": serialize_order(order),
        "licenses_minted": len(licenses),
        "licenses": [
            {
                "id": lic.id,
                "seat_index": lic.seat_index,
                "product_id": lic.product_id,
                "status": lic.status,
                "key_prefix": lic.key_prefix,
                "key_last4": lic.key_last4,
                "bound_device_id": lic.bound_device_id,
                "expires_at": lic.expires_at.isoformat() if lic.expires_at else None,
            }
            for lic in licenses
        ],
        "email_delivery": email_out,
    }


@router.post("/payment-requests/{payment_id}/reject", response_model=DesktopPaymentOut)
def admin_reject_payment(
    payment_id: int,
    body: DesktopPaymentRejectBody,
    _: None = Depends(require_desktop_licensing_enabled),
    admin: PlatformAdmin = Depends(get_platform_admin),
    db: Session = Depends(get_db_session),
):
    from app.licensing.payments import reject_payment, serialize_payment

    try:
        payment, _order = reject_payment(db, admin=admin, payment_id=payment_id, reason=body.reason)
        db.commit()
        db.refresh(payment)
    except Exception:
        db.rollback()
        raise
    return serialize_payment(payment)


@router.get("/licenses", response_model=list[DesktopLicenseOut])
def admin_list_licenses(
    _: None = Depends(require_desktop_licensing_enabled),
    admin: PlatformAdmin = Depends(get_platform_admin),
    db: Session = Depends(get_db_session),
    user_id: int | None = None,
    limit: int = 200,
):
    del admin
    from app.licensing.customer_licenses import list_licenses_admin, serialize_license_public

    return [
        serialize_license_public(lic, order=lic.order)
        for lic in list_licenses_admin(db, limit=limit, user_id=user_id)
    ]


@router.post("/licenses/{license_id}/reveal", response_model=DesktopLicenseRevealOut)
def admin_reveal_license(
    license_id: int,
    _: None = Depends(require_desktop_licensing_enabled),
    admin: PlatformAdmin = Depends(get_platform_admin),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    """Explicit authorized admin reveal — audited; not used by default list UI."""
    from app.licensing.customer_licenses import masked_key_from_parts, reveal_license_key_for_admin
    from app.licensing.models import DesktopLicense

    try:
        plaintext = reveal_license_key_for_admin(db, settings, admin=admin, license_id=license_id)
        lic = db.get(DesktopLicense, int(license_id))
        db.commit()
    except Exception:
        db.rollback()
        raise
    assert lic is not None
    return {
        "license_id": lic.id,
        "seat_index": lic.seat_index,
        "license_key": plaintext,
        "key_masked": masked_key_from_parts(lic.key_prefix, lic.key_last4),
    }


@router.post(
    "/orders/{order_id}/resend-license-email",
    response_model=DesktopLicenseEmailDeliveryOut,
)
def admin_resend_license_email(
    order_id: int,
    _: None = Depends(require_desktop_licensing_enabled),
    admin: PlatformAdmin = Depends(get_platform_admin),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    from app.licensing.customer_licenses import (
        resend_license_email_for_admin,
        serialize_email_delivery,
    )

    try:
        delivery = resend_license_email_for_admin(db, settings, admin=admin, order_id=order_id)
        db.commit()
        db.refresh(delivery)
    except Exception:
        db.rollback()
        raise
    return serialize_email_delivery(delivery)
