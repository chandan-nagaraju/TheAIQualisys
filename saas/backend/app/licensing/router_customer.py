"""Customer desktop licensing routes (catalog, orders, Phase 4 payments)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
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
    DesktopDownloadProductOut,
    DesktopDownloadRedeemOut,
    DesktopDownloadTokenOut,
    DesktopLicenseEmailDeliveryOut,
    DesktopLicenseOut,
    DesktopLicenseRevealOut,
    DesktopOrderCreate,
    DesktopOrderOut,
    DesktopPaymentOut,
    DesktopProductWithPlansOut,
    DesktopTrialCreate,
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
    out["phase"] = "6-protected-downloads"
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


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for") or ""
    if forwarded:
        return forwarded.split(",")[0].strip() or "unknown"
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


@router.post("/trials", response_model=DesktopLicenseOut, status_code=201)
def customer_create_trial(
    body: DesktopTrialCreate,
    request: Request,
    _: None = Depends(require_desktop_licensing_enabled),
    user: CompanyUser = Depends(get_current_company_user),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    """Start a 7-day desktop trial. One trial ever per (user, product). No plaintext in response."""
    from app.licensing.trials import (
        apply_trial_create_rate_limits,
        attempt_send_trial_email,
        create_desktop_trial,
        serialize_trial_create_response,
    )

    apply_trial_create_rate_limits(user_id=int(user.id), client_ip=_client_ip(request))
    try:
        license_row, product, _delivery = create_desktop_trial(
            db,
            settings,
            user=user,
            product_code=body.product_code,
        )
        db.commit()
        db.refresh(license_row)
    except Exception:
        db.rollback()
        raise

    # Email after commit — failure must not undo the trial license
    try:
        attempt_send_trial_email(
            db,
            settings,
            license_id=int(license_row.id),
            actor_type="user",
            actor_id=int(user.id),
            is_resend=False,
            enforce_rate_limit=False,
        )
        db.commit()
    except Exception:
        db.rollback()
        # Soft-fail: license remains issued
        pass

    return serialize_trial_create_response(license_row, product=product)


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


@router.get("/licenses", response_model=list[DesktopLicenseOut])
def customer_list_licenses(
    _: None = Depends(require_desktop_licensing_enabled),
    user: CompanyUser = Depends(get_current_company_user),
    db: Session = Depends(get_db_session),
    limit: int = 200,
):
    from app.licensing.customer_licenses import list_licenses_for_user, serialize_license_public
    from app.licensing.models import DesktopLicenseEmailDelivery, DesktopProduct, DesktopTrialEmailDelivery
    from sqlalchemy import select

    rows = list_licenses_for_user(db, user=user, limit=limit)
    # Attach email status when order has a delivery row
    order_ids = {int(r.order_id) for r in rows if r.order_id}
    deliveries = {}
    if order_ids:
        for d in db.execute(
            select(DesktopLicenseEmailDelivery).where(DesktopLicenseEmailDelivery.order_id.in_(order_ids))
        ).scalars().all():
            deliveries[int(d.order_id)] = d
    trial_license_ids = {
        int(r.id) for r in rows if (r.entitlement_type or "").lower() == "trial"
    }
    trial_deliveries = {}
    if trial_license_ids:
        for d in db.execute(
            select(DesktopTrialEmailDelivery).where(
                DesktopTrialEmailDelivery.license_id.in_(trial_license_ids)
            )
        ).scalars().all():
            trial_deliveries[int(d.license_id)] = d
    product_ids = {int(r.product_id) for r in rows if not r.order_id}
    products = {}
    if product_ids:
        for p in db.execute(select(DesktopProduct).where(DesktopProduct.id.in_(product_ids))).scalars().all():
            products[int(p.id)] = p
    out = []
    for lic in rows:
        email_delivery = deliveries.get(int(lic.order_id)) if lic.order_id else None
        # Map trial email onto the same email_status fields for UI
        trial_delivery = trial_deliveries.get(int(lic.id))
        if email_delivery is None and trial_delivery is not None:
            # Lightweight adapter: serialize_license_public reads .status / .sent_at
            email_delivery = trial_delivery
        out.append(
            serialize_license_public(
                lic,
                order=lic.order,
                product=None if lic.order_id else products.get(int(lic.product_id)),
                email_delivery=email_delivery,
            )
        )
    return out


@router.get("/licenses/{license_id}", response_model=DesktopLicenseOut)
def customer_get_license(
    license_id: int,
    _: None = Depends(require_desktop_licensing_enabled),
    user: CompanyUser = Depends(get_current_company_user),
    db: Session = Depends(get_db_session),
):
    from app.licensing.customer_licenses import get_owned_license, serialize_license_public
    from app.licensing.models import DesktopLicenseEmailDelivery
    from sqlalchemy import select

    lic = get_owned_license(db, user=user, license_id=license_id)
    delivery = None
    if lic.order_id:
        delivery = db.execute(
            select(DesktopLicenseEmailDelivery).where(
                DesktopLicenseEmailDelivery.order_id == int(lic.order_id)
            )
        ).scalar_one_or_none()
    return serialize_license_public(lic, order=lic.order, email_delivery=delivery)


@router.post("/licenses/{license_id}/reveal", response_model=DesktopLicenseRevealOut)
def customer_reveal_license(
    license_id: int,
    _: None = Depends(require_desktop_licensing_enabled),
    user: CompanyUser = Depends(get_current_company_user),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    from app.licensing.customer_licenses import (
        get_owned_license,
        masked_key_from_parts,
        reveal_license_key_for_user,
    )

    try:
        plaintext = reveal_license_key_for_user(db, settings, user=user, license_id=license_id)
        lic = get_owned_license(db, user=user, license_id=license_id)
        db.commit()
    except Exception:
        db.rollback()
        raise
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
def customer_resend_license_email(
    order_id: int,
    _: None = Depends(require_desktop_licensing_enabled),
    user: CompanyUser = Depends(get_current_company_user),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    from app.licensing.customer_licenses import (
        resend_license_email_for_customer,
        serialize_email_delivery,
    )

    try:
        delivery = resend_license_email_for_customer(db, settings, user=user, order_id=order_id)
        db.commit()
        db.refresh(delivery)
    except Exception:
        db.rollback()
        raise
    return serialize_email_delivery(delivery)


@router.get(
    "/orders/{order_id}/license-email-status",
    response_model=DesktopLicenseEmailDeliveryOut | None,
)
def customer_license_email_status(
    order_id: int,
    _: None = Depends(require_desktop_licensing_enabled),
    user: CompanyUser = Depends(get_current_company_user),
    db: Session = Depends(get_db_session),
):
    from app.licensing.customer_licenses import (
        get_email_delivery_for_customer_order,
        serialize_email_delivery,
    )

    row = get_email_delivery_for_customer_order(db, user=user, order_id=order_id)
    if not row:
        return None
    return serialize_email_delivery(row)


@router.get("/downloads", response_model=list[DesktopDownloadProductOut])
def customer_list_downloads(
    _: None = Depends(require_desktop_licensing_enabled),
    user: CompanyUser = Depends(get_current_company_user),
    db: Session = Depends(get_db_session),
):
    from app.licensing.downloads import list_customer_downloads

    return list_customer_downloads(db, user=user)


@router.get("/downloads/products/{product_code}", response_model=DesktopDownloadProductOut)
def customer_product_downloads(
    product_code: str,
    _: None = Depends(require_desktop_licensing_enabled),
    user: CompanyUser = Depends(get_current_company_user),
    db: Session = Depends(get_db_session),
):
    from app.licensing.downloads import list_customer_product_versions

    return list_customer_product_versions(db, user=user, product_code=product_code)


@router.post(
    "/downloads/installers/{installer_id}/token",
    response_model=DesktopDownloadTokenOut,
)
def customer_mint_download_token(
    installer_id: int,
    _: None = Depends(require_desktop_licensing_enabled),
    user: CompanyUser = Depends(get_current_company_user),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    from app.licensing.downloads import mint_download_token

    try:
        raw, token = mint_download_token(db, settings, user=user, installer_id=installer_id)
        db.commit()
    except Exception:
        db.rollback()
        raise
    ttl = int(settings.installer_download_token_ttl_seconds or 120)
    ttl = max(60, min(ttl, 300))
    return {"token": raw, "expires_in_seconds": ttl, "installer_id": installer_id}


@router.get("/downloads/redeem/{token}", response_model=DesktopDownloadRedeemOut)
def customer_redeem_download_token(
    token: str,
    _: None = Depends(require_desktop_licensing_enabled),
    user: CompanyUser = Depends(get_current_company_user),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    from app.licensing.downloads import redeem_download_token

    try:
        out = redeem_download_token(db, settings, user=user, raw_token=token)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return out
