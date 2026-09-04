"""Admin catalog/pricing routes for desktop licensing (Phase 2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import Settings, get_settings
from app.deps import get_db_session, get_platform_admin
from app.licensing.feature_flag import require_desktop_licensing_enabled
from app.licensing.models import DesktopProduct
from app.licensing.orders import list_all_orders_admin, serialize_order
from app.licensing.schemas import (
    DesktopInstallerAdminOut,
    DesktopInstallerChannelBody,
    DesktopInstallerCreate,
    DesktopInstallerPatch,
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
    LicenseDeviceResetIn,
    LicenseDeviceResetOut,
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
    out["phase"] = "6-protected-downloads"
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
    from app.licensing.models import DesktopProduct
    from sqlalchemy import select

    rows = list_licenses_admin(db, limit=limit, user_id=user_id)
    product_ids = {int(r.product_id) for r in rows if not r.order_id}
    products = {}
    if product_ids:
        for p in db.execute(select(DesktopProduct).where(DesktopProduct.id.in_(product_ids))).scalars().all():
            products[int(p.id)] = p
    return [
        serialize_license_public(
            lic,
            order=lic.order,
            product=None if lic.order_id else products.get(int(lic.product_id)),
        )
        for lic in rows
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


@router.post("/licenses/{license_id}/reset-device", response_model=LicenseDeviceResetOut)
def admin_reset_license_device(
    license_id: int,
    body: LicenseDeviceResetIn,
    _: None = Depends(require_desktop_licensing_enabled),
    admin: PlatformAdmin = Depends(get_platform_admin),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    """Platform-admin machine replacement — clears binding; does not auto-activate."""
    from app.licensing.binding import admin_reset_device_binding
    from app.licensing.constants import ADMIN_RESET_REASON_MIN_LEN
    from app.licensing.machine import machine_http_error
    from app.licensing.constants import MACHINE_ERR_INVALID_LICENSE, MACHINE_ERR_INVALID_REQUEST
    from app.licensing.models import DesktopLicense
    from app.licensing.rate_limit import check_rate_limit
    from app.licensing.service import record_license_event

    del settings
    check_rate_limit(scope="admin_license_reset", key=str(admin.id), limit=20)
    reason = (body.reason or "").strip()
    if len(reason) < ADMIN_RESET_REASON_MIN_LEN:
        raise machine_http_error(
            MACHINE_ERR_INVALID_REQUEST,
            f"reason must be at least {ADMIN_RESET_REASON_MIN_LEN} characters",
            http_status=400,
        )
    lic = db.get(DesktopLicense, int(license_id))
    if not lic:
        raise machine_http_error(MACHINE_ERR_INVALID_LICENSE, "License not found", http_status=404)
    try:
        result = admin_reset_device_binding(db, license_row=lic, admin_id=admin.id)
        record_license_event(
            db,
            license_id=result.license.id,
            actor_type="admin",
            actor_id=admin.id,
            event_type="license_device_reset",
            meta={
                "previous_activation_id": result.previous_activation_id,
                "previous_device_id": result.previous_device_id,
                "reason": reason,
                # never log plaintext key / tokens / secrets
            },
        )
        db.commit()
        db.refresh(result.license)
    except Exception:
        db.rollback()
        raise
    return {
        "license_id": result.license.id,
        "status": result.license.status,
        "bound_device_id": result.license.bound_device_id,
        "previous_activation_id": result.previous_activation_id,
        "previous_device_id": result.previous_device_id,
        "reason": reason,
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


@router.get("/products/{product_id}/installers", response_model=list[DesktopInstallerAdminOut])
def admin_list_installers(
    product_id: int,
    _: None = Depends(require_desktop_licensing_enabled),
    admin: PlatformAdmin = Depends(get_platform_admin),
    db: Session = Depends(get_db_session),
):
    del admin
    from app.licensing.downloads import list_installers_admin, serialize_installer_admin
    from app.licensing.service import get_product_or_404

    product = get_product_or_404(db, product_id)
    return [serialize_installer_admin(r, product=product) for r in list_installers_admin(db, product_id=product.id)]


@router.post("/products/{product_id}/installers", response_model=DesktopInstallerAdminOut, status_code=201)
def admin_create_installer(
    product_id: int,
    body: DesktopInstallerCreate,
    _: None = Depends(require_desktop_licensing_enabled),
    admin: PlatformAdmin = Depends(get_platform_admin),
    db: Session = Depends(get_db_session),
):
    from datetime import date as date_cls

    from app.licensing.downloads import create_installer_version, serialize_installer_admin
    from app.licensing.service import get_product_or_404

    product = get_product_or_404(db, product_id)
    rd = None
    if body.release_date:
        rd = date_cls.fromisoformat(body.release_date)
    try:
        row = create_installer_version(
            db,
            admin=admin,
            product_id=product.id,
            version=body.version,
            release_notes=body.release_notes,
            release_date=rd,
            min_windows_version=body.min_windows_version,
            min_supported_version=body.min_supported_version,
        )
        db.commit()
        db.refresh(row)
    except Exception:
        db.rollback()
        raise
    return serialize_installer_admin(row, product=product)


@router.post("/installers/{installer_id}/upload", response_model=DesktopInstallerAdminOut)
async def admin_upload_installer(
    installer_id: int,
    _: None = Depends(require_desktop_licensing_enabled),
    admin: PlatformAdmin = Depends(get_platform_admin),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    file: UploadFile = File(...),
):
    from app.licensing.downloads import serialize_installer_admin, upload_installer_file
    from app.licensing.service import get_product_or_404

    try:
        row = await upload_installer_file(db, settings, admin=admin, installer_id=installer_id, file=file)
        product = get_product_or_404(db, row.product_id)
        db.commit()
        db.refresh(row)
    except Exception:
        db.rollback()
        raise
    return serialize_installer_admin(row, product=product)


@router.patch("/installers/{installer_id}", response_model=DesktopInstallerAdminOut)
def admin_patch_installer(
    installer_id: int,
    body: DesktopInstallerPatch,
    _: None = Depends(require_desktop_licensing_enabled),
    admin: PlatformAdmin = Depends(get_platform_admin),
    db: Session = Depends(get_db_session),
):
    from datetime import date as date_cls

    from app.licensing.downloads import patch_installer, serialize_installer_admin
    from app.licensing.service import get_product_or_404

    rd = date_cls.fromisoformat(body.release_date) if body.release_date else None
    try:
        row = patch_installer(
            db,
            admin=admin,
            installer_id=installer_id,
            release_notes=body.release_notes,
            release_date=rd,
            min_windows_version=body.min_windows_version,
            min_supported_version=body.min_supported_version,
            clear_notes=body.clear_notes,
        )
        product = get_product_or_404(db, row.product_id)
        db.commit()
        db.refresh(row)
    except Exception:
        db.rollback()
        raise
    return serialize_installer_admin(row, product=product)


@router.post("/installers/{installer_id}/publish", response_model=DesktopInstallerAdminOut)
def admin_publish_installer(
    installer_id: int,
    _: None = Depends(require_desktop_licensing_enabled),
    admin: PlatformAdmin = Depends(get_platform_admin),
    db: Session = Depends(get_db_session),
):
    from app.licensing.downloads import serialize_installer_admin, set_installer_listing
    from app.licensing.service import get_product_or_404

    try:
        row = set_installer_listing(db, admin=admin, installer_id=installer_id, listing_active=True)
        product = get_product_or_404(db, row.product_id)
        db.commit()
        db.refresh(row)
    except Exception:
        db.rollback()
        raise
    return serialize_installer_admin(row, product=product)


@router.post("/installers/{installer_id}/unpublish", response_model=DesktopInstallerAdminOut)
def admin_unpublish_installer(
    installer_id: int,
    _: None = Depends(require_desktop_licensing_enabled),
    admin: PlatformAdmin = Depends(get_platform_admin),
    db: Session = Depends(get_db_session),
):
    from app.licensing.downloads import serialize_installer_admin, set_installer_listing
    from app.licensing.service import get_product_or_404

    try:
        row = set_installer_listing(db, admin=admin, installer_id=installer_id, listing_active=False)
        product = get_product_or_404(db, row.product_id)
        db.commit()
        db.refresh(row)
    except Exception:
        db.rollback()
        raise
    return serialize_installer_admin(row, product=product)


@router.post("/installers/{installer_id}/set-channel", response_model=DesktopInstallerAdminOut)
def admin_set_installer_channel(
    installer_id: int,
    body: DesktopInstallerChannelBody,
    _: None = Depends(require_desktop_licensing_enabled),
    admin: PlatformAdmin = Depends(get_platform_admin),
    db: Session = Depends(get_db_session),
):
    from app.licensing.downloads import serialize_installer_admin, set_installer_channel
    from app.licensing.service import get_product_or_404

    try:
        row = set_installer_channel(db, admin=admin, installer_id=installer_id, channel=body.channel)
        product = get_product_or_404(db, row.product_id)
        db.commit()
        db.refresh(row)
    except Exception:
        db.rollback()
        raise
    return serialize_installer_admin(row, product=product)
