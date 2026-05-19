from datetime import date, timedelta

from app.dates import billing_month_year_english, billing_today

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.deps import get_db_session, get_platform_admin
from app.email_util import (
    build_admin_manual_subscription_reminder_email,
    build_admin_thank_you_performance_email,
    is_email_configured,
    send_plain_text_email,
)
from app.fir_analytics import build_fir_intelligence, list_fir_invoice_months
from app.models import (
    AdminSubscriptionReminder,
    Company,
    CompanySettings,
    CompanyUser,
    Customer,
    FirReportEvent,
    FirUploadLog,
    InvoiceV2,
    ModulePricing,
    PartV2,
    PlanType,
    PlatformAdmin,
    SubscriptionStatus,
)
from app.module_access import resync_qms_trials_after_pricing_change
from app.pricing_catalog import list_all_pricing_rows
from app.schemas import (
    AdminCompanyPatch,
    AdminCompanySummary,
    AdminDashboardResponse,
    AdminFirCustomerRow,
    AdminLoginRequest,
    AdminSubscriptionReminderSendBody,
    AdminSubscriptionReminderSendResponse,
    AdminTenantUserRow,
    CompanyOut,
    ModulePricingPatch,
    ModulePricingPublicOut,
    TokenResponse,
)
from app.security import (
    create_access_token,
    create_admin_token,
    verify_password_and_upgrade,
)
from app.subscription_logic import (
    count_fir_reports_this_month,
    count_fir_reports_total,
    count_invoices_this_month,
    sync_subscription_status_from_dates,
    top_fir_part_report_counts,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def _company_out(c: Company) -> CompanyOut:
    return CompanyOut.model_validate(c)


@router.post("/login", response_model=TokenResponse)
def admin_login(body: AdminLoginRequest, db: Session = Depends(get_db_session)):
    admin = db.execute(select(PlatformAdmin).where(PlatformAdmin.email == str(body.email).lower())).scalar_one_or_none()
    if not admin:
        raise HTTPException(status_code=401, detail="Invalid admin credentials")
    ok, upgraded_hash = verify_password_and_upgrade(body.password, admin.password_hash)
    if not ok:
        raise HTTPException(status_code=401, detail="Invalid admin credentials")
    if upgraded_hash:
        admin.password_hash = upgraded_hash
        db.add(admin)
        db.commit()
    token = create_admin_token(str(admin.id))
    return TokenResponse(access_token=token)


@router.get("/dashboard", response_model=AdminDashboardResponse)
def admin_dashboard(
    _: PlatformAdmin = Depends(get_platform_admin),
    db: Session = Depends(get_db_session),
):
    today = billing_today()
    companies = db.execute(select(Company)).scalars().all()
    changed = False
    for c in companies:
        if sync_subscription_status_from_dates(c, today):
            db.add(c)
            changed = True
    if changed:
        db.commit()
    total = db.execute(select(func.count()).select_from(Company)).scalar_one()
    trial = db.execute(
        select(func.count()).select_from(Company).where(Company.subscription_status == SubscriptionStatus.trial.value)
    ).scalar_one()
    active = db.execute(
        select(func.count()).select_from(Company).where(Company.subscription_status == SubscriptionStatus.active.value)
    ).scalar_one()
    expired = db.execute(
        select(func.count()).select_from(Company).where(Company.subscription_status == SubscriptionStatus.expired.value)
    ).scalar_one()
    inv = db.execute(select(func.count()).select_from(InvoiceV2)).scalar_one()
    return AdminDashboardResponse(
        total_companies=int(total),
        trial_count=int(trial),
        active_count=int(active),
        expired_count=int(expired),
        total_invoices=int(inv),
    )


@router.get("/tenant-users", response_model=list[AdminTenantUserRow])
def list_all_tenant_users(
    _: PlatformAdmin = Depends(get_platform_admin),
    db: Session = Depends(get_db_session),
):
    """All company-user logins across tenants (support: who can sign in per company)."""
    rows = (
        db.execute(
            select(CompanyUser, Company)
            .join(Company, CompanyUser.company_id == Company.id)
            .order_by(Company.company_name, CompanyUser.email)
        )
        .all()
    )
    today = billing_today()
    seen: set[int] = set()
    changed = False
    for _u, co in rows:
        if co.id in seen:
            continue
        seen.add(co.id)
        if sync_subscription_status_from_dates(co, today):
            db.add(co)
            changed = True
    if changed:
        db.commit()
        for _u, co in rows:
            db.refresh(co)
    return [
        AdminTenantUserRow(
            user_id=u.id,
            email=u.email,
            name=u.name,
            is_blocked=bool(getattr(u, "is_blocked", 0)),
            created_at=u.created_at,
            company_id=c.id,
            company_name=c.company_name,
            company_vendor_code=c.vendor_code,
            plan_type=c.plan_type,
            subscription_status=c.subscription_status,
        )
        for u, c in rows
    ]


@router.post("/tenant-users/{user_id}/block")
def block_tenant_user(
    user_id: int,
    _: PlatformAdmin = Depends(get_platform_admin),
    db: Session = Depends(get_db_session),
):
    user = db.get(CompanyUser, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Tenant user not found")
    user.is_blocked = 1
    db.add(user)
    db.commit()
    return {"ok": True, "user_id": user.id, "is_blocked": True}


@router.post("/tenant-users/{user_id}/unblock")
def unblock_tenant_user(
    user_id: int,
    _: PlatformAdmin = Depends(get_platform_admin),
    db: Session = Depends(get_db_session),
):
    user = db.get(CompanyUser, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Tenant user not found")
    user.is_blocked = 0
    db.add(user)
    db.commit()
    return {"ok": True, "user_id": user.id, "is_blocked": False}


@router.delete("/tenant-users/{user_id}")
def delete_tenant_user(
    user_id: int,
    _: PlatformAdmin = Depends(get_platform_admin),
    db: Session = Depends(get_db_session),
):
    user = db.get(CompanyUser, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Tenant user not found")
    company_id = int(user.company_id)
    db.execute(delete(CompanyUser).where(CompanyUser.id == user_id))
    db.commit()
    remaining = db.execute(
        select(func.count(CompanyUser.id)).where(CompanyUser.company_id == company_id)
    ).scalar_one()
    n = int(remaining or 0)
    return {
        "ok": True,
        "deleted_user_id": user_id,
        "company_id": company_id,
        "remaining_tenant_users": n,
    }


@router.get("/fir-customers", response_model=list[AdminFirCustomerRow])
def list_all_fir_customers(
    _: PlatformAdmin = Depends(get_platform_admin),
    db: Session = Depends(get_db_session),
):
    """All FIR customers (vendor master) across tenants (upload / inspection context)."""
    rows = (
        db.execute(
            select(Customer, Company)
            .join(Company, Customer.company_id == Company.id)
            .order_by(Company.company_name, Customer.name)
        )
        .all()
    )
    return [
        AdminFirCustomerRow(
            customer_id=cust.id,
            vendor_code=cust.vendor_code,
            name=cust.name,
            company_id=co.id,
            company_name=co.company_name,
            company_vendor_code=co.vendor_code,
        )
        for cust, co in rows
    ]


@router.post("/companies/{company_id}/impersonate", response_model=TokenResponse)
def impersonate_company(
    company_id: int,
    _: PlatformAdmin = Depends(get_platform_admin),
    db: Session = Depends(get_db_session),
):
    """Return a company JWT for the first user of this tenant (platform admin support / workspace access)."""
    user = db.execute(
        select(CompanyUser).where(CompanyUser.company_id == company_id).order_by(CompanyUser.id)
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="No company user for this tenant")
    token = create_access_token(
        str(user.id),
        {"company_id": user.company_id, "impersonated_by_admin": True},
    )
    return TokenResponse(access_token=token)


@router.get("/companies", response_model=list[AdminCompanySummary])
def list_companies(
    _: PlatformAdmin = Depends(get_platform_admin),
    db: Session = Depends(get_db_session),
):
    companies = db.execute(select(Company).order_by(Company.id)).scalars().all()
    today = billing_today()
    changed = False
    for c in companies:
        if sync_subscription_status_from_dates(c, today):
            db.add(c)
            changed = True
    if changed:
        db.commit()
        for c in companies:
            db.refresh(c)
    uid_rows = db.execute(
        select(CompanyUser.company_id, func.count(CompanyUser.id)).group_by(CompanyUser.company_id)
    ).all()
    user_count_by_company = {int(cid): int(n) for cid, n in uid_rows}
    out: list[AdminCompanySummary] = []
    for c in companies:
        inv = count_invoices_this_month(db, c.id, today)
        fir = count_fir_reports_this_month(db, c.id, today)
        out.append(
            AdminCompanySummary(
                id=c.id,
                company_name=c.company_name,
                vendor_code=c.vendor_code,
                plan_type=c.plan_type,
                subscription_status=c.subscription_status,
                monthly_usage=inv,
                monthly_fir_reports=fir,
                monthly_usage_combined=inv + fir,
                tenant_user_count=user_count_by_company.get(c.id, 0),
            )
        )
    return out


@router.get("/companies/{company_id}", response_model=CompanyOut)
def get_company(
    company_id: int,
    _: PlatformAdmin = Depends(get_platform_admin),
    db: Session = Depends(get_db_session),
):
    c = db.get(Company, company_id)
    if not c:
        raise HTTPException(status_code=404, detail="Company not found")
    if sync_subscription_status_from_dates(c, billing_today()):
        db.add(c)
        db.commit()
        db.refresh(c)
    return _company_out(c)


@router.patch("/companies/{company_id}", response_model=CompanyOut)
def patch_company(
    company_id: int,
    body: AdminCompanyPatch,
    _: PlatformAdmin = Depends(get_platform_admin),
    db: Session = Depends(get_db_session),
):
    c = db.get(Company, company_id)
    if not c:
        raise HTTPException(status_code=404, detail="Company not found")

    today = billing_today()

    if body.action == "activate":
        end = body.subscription_end or (today + timedelta(days=30))
        start = body.subscription_start or today
        c.subscription_status = SubscriptionStatus.active.value
        c.subscription_start = start
        c.subscription_end = end
        if body.plan_type:
            if body.plan_type not in (PlanType.basic.value, PlanType.pro.value, PlanType.enterprise.value):
                raise HTTPException(status_code=400, detail="Invalid plan_type")
            c.plan_type = body.plan_type

    elif body.action == "extend":
        if not body.extend_days and body.subscription_end is None:
            raise HTTPException(status_code=400, detail="Provide extend_days or subscription_end")
        base = c.subscription_end or today
        if body.subscription_end:
            c.subscription_end = body.subscription_end
        elif body.extend_days:
            c.subscription_end = base + timedelta(days=body.extend_days)
        if c.subscription_status == SubscriptionStatus.expired.value:
            c.subscription_status = SubscriptionStatus.active.value
        if c.subscription_start is None:
            c.subscription_start = today

    elif body.action == "set_plan":
        if not body.plan_type:
            raise HTTPException(status_code=400, detail="plan_type required")
        if body.plan_type not in (PlanType.basic.value, PlanType.pro.value, PlanType.enterprise.value):
            raise HTTPException(status_code=400, detail="Invalid plan_type")
        c.plan_type = body.plan_type

    elif body.action == "mark_expired":
        c.subscription_status = SubscriptionStatus.expired.value
        yday = today - timedelta(days=1)
        if c.subscription_end is None or c.subscription_end >= today:
            c.subscription_end = yday

    else:
        raise HTTPException(status_code=400, detail="Unknown action")

    sync_subscription_status_from_dates(c, today)
    db.commit()
    db.refresh(c)
    return _company_out(c)


@router.post(
    "/companies/{company_id}/subscription-reminder",
    response_model=AdminSubscriptionReminderSendResponse,
)
def send_manual_subscription_reminder(
    company_id: int,
    body: AdminSubscriptionReminderSendBody,
    _: PlatformAdmin = Depends(get_platform_admin),
    db: Session = Depends(get_db_session),
):
    """Send a subscription reminder email to all non-blocked workspace users for this tenant."""
    settings = get_settings()
    if not is_email_configured(settings):
        raise HTTPException(status_code=503, detail="Email is not configured (Resend or SMTP + EMAIL_FROM).")

    c = db.get(Company, company_id)
    if not c:
        raise HTTPException(status_code=404, detail="Company not found")

    today = billing_today()
    if sync_subscription_status_from_dates(c, today):
        db.add(c)
        db.commit()
        db.refresh(c)

    users = (
        db.execute(
            select(CompanyUser).where(
                CompanyUser.company_id == company_id,
                CompanyUser.is_blocked == 0,
            )
        )
        .scalars()
        .all()
    )
    if not users:
        raise HTTPException(
            status_code=400,
            detail="No active (non-blocked) workspace users to email for this tenant.",
        )

    if body.reminder_type in ("ending_soon", "already_ended") and c.subscription_end is None:
        raise HTTPException(
            status_code=400,
            detail="This tenant has no subscription end date; activate or extend the subscription first.",
        )

    report_total = count_fir_reports_total(db, company_id)
    report_month = count_fir_reports_this_month(db, company_id, today)
    current_month_name = billing_month_year_english(today)
    plan_name = c.plan_type.title()

    if body.reminder_type == "thank_you_performance":
        sub_start = c.subscription_start.strftime("%B %d, %Y") if c.subscription_start else "—"
        sub_end = c.subscription_end.strftime("%B %d, %Y") if c.subscription_end else "—"
        top_parts = top_fir_part_report_counts(db, company_id, limit=5)
        subject, text = build_admin_thank_you_performance_email(
            customer_name=c.company_name,
            plan_name=plan_name,
            subscription_start_date=sub_start,
            subscription_end_date=sub_end,
            current_month_name=current_month_name,
            current_month_report_count=report_month,
            total_report_count=report_total,
            workspace_user_count=len(users),
            top_parts=top_parts,
        )
    else:
        assert c.subscription_end is not None  # guarded above for ending/already
        end_date_display = c.subscription_end.strftime("%B %d, %Y")
        renewal_link = f"{settings.public_app_url.rstrip('/')}/dashboard/billing"
        subject, text = build_admin_manual_subscription_reminder_email(
            reminder_type=body.reminder_type,
            customer_name=c.company_name,
            plan_name=plan_name,
            end_date_display=end_date_display,
            current_month_name=current_month_name,
            current_month_report_count=report_month,
            total_report_count=report_total,
            renewal_link=renewal_link,
        )

    errors: list[str] = []
    sent = 0
    for u in users:
        try:
            send_plain_text_email(settings, u.email, subject, text)
            sent += 1
        except Exception as exc:  # noqa: BLE001 — surface provider errors to admin
            errors.append(f"{u.email}: {exc}")

    n = len(users)
    if sent == n:
        st = "success"
        err_msg = None
    elif sent == 0:
        st = "failed"
        err_msg = "; ".join(errors)[:8000]
    else:
        st = "partial"
        err_msg = "; ".join(errors)[:8000]

    db.add(
        AdminSubscriptionReminder(
            company_id=company_id,
            reminder_type=body.reminder_type,
            reports_generated=report_total,
            email_status=st,
            error_message=err_msg,
        )
    )
    db.commit()

    if sent == 0:
        raise HTTPException(
            status_code=502,
            detail={"message": "Failed to send to all recipients", "errors": errors},
        )

    return AdminSubscriptionReminderSendResponse(
        email_status=st,
        total_report_count=report_total,
        current_month_report_count=report_month,
        current_month_name=current_month_name,
        recipients_attempted=n,
        emails_sent=sent,
    )


@router.delete("/companies/{company_id}")
def delete_tenant_company(
    company_id: int,
    _: PlatformAdmin = Depends(get_platform_admin),
    db: Session = Depends(get_db_session),
):
    """Permanently remove a tenant and all related workspace data (admin offboarding).

    Order respects ``parts_v2.customer_id`` → ``fir_customers`` **RESTRICT** (parts deleted first).
    """
    c = db.get(Company, company_id)
    if not c:
        raise HTTPException(status_code=404, detail="Company not found")
    cid = company_id
    db.execute(delete(FirReportEvent).where(FirReportEvent.company_id == cid))
    db.execute(delete(FirUploadLog).where(FirUploadLog.company_id == cid))
    db.execute(delete(PartV2).where(PartV2.company_id == cid))
    db.execute(delete(Customer).where(Customer.company_id == cid))
    db.execute(delete(InvoiceV2).where(InvoiceV2.company_id == cid))
    db.execute(delete(CompanyUser).where(CompanyUser.company_id == cid))
    db.execute(delete(CompanySettings).where(CompanySettings.company_id == cid))
    db.execute(delete(Company).where(Company.id == cid))
    db.commit()
    return {"ok": True, "deleted_company_id": company_id}


@router.get("/companies/{company_id}/users", response_model=list[dict])
def company_users(
    company_id: int,
    _: PlatformAdmin = Depends(get_platform_admin),
    db: Session = Depends(get_db_session),
):
    c = db.get(Company, company_id)
    if not c:
        raise HTTPException(status_code=404, detail="Company not found")
    users = db.execute(select(CompanyUser).where(CompanyUser.company_id == company_id)).scalars().all()
    return [{"id": u.id, "email": u.email, "name": u.name} for u in users]


@router.get("/companies/{company_id}/usage")
def company_usage(
    company_id: int,
    _: PlatformAdmin = Depends(get_platform_admin),
    db: Session = Depends(get_db_session),
):
    c = db.get(Company, company_id)
    if not c:
        raise HTTPException(status_code=404, detail="Company not found")
    today = billing_today()
    if sync_subscription_status_from_dates(c, today):
        db.add(c)
        db.commit()
        db.refresh(c)
    inv = count_invoices_this_month(db, company_id, today)
    fir = count_fir_reports_this_month(db, company_id, today)
    return {
        "company_id": company_id,
        "monthly_invoice_count": inv,
        "monthly_fir_reports": fir,
        "monthly_usage_combined": inv + fir,
        "trial_start": c.trial_start_date.isoformat(),
        "trial_end": c.trial_end_date.isoformat(),
        "subscription_start": c.subscription_start.isoformat() if c.subscription_start else None,
        "subscription_end": c.subscription_end.isoformat() if c.subscription_end else None,
        "plan_type": c.plan_type,
        "subscription_status": c.subscription_status,
    }


@router.get("/companies/{company_id}/fir-intelligence-months")
def company_fir_intelligence_months(
    company_id: int,
    _: PlatformAdmin = Depends(get_platform_admin),
    db: Session = Depends(get_db_session),
):
    """Months that have at least one fir_events row (by invoice_date), for the admin month picker."""
    c = db.get(Company, company_id)
    if not c:
        raise HTTPException(status_code=404, detail="Company not found")
    return list_fir_invoice_months(db, company_id)


@router.get("/companies/{company_id}/fir-intelligence")
def company_fir_intelligence(
    company_id: int,
    year: int | None = Query(None, ge=2000, le=2100),
    month: int | None = Query(None, ge=1, le=12),
    _: PlatformAdmin = Depends(get_platform_admin),
    db: Session = Depends(get_db_session),
):
    c = db.get(Company, company_id)
    if not c:
        raise HTTPException(status_code=404, detail="Company not found")
    if year is None:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "year_required",
                "message": "Pass `year` as the April-start year of the Indian FY when using a full-year rollup "
                "(e.g. ?year=2026 → Apr 2026–Mar 2027). Single calendar month: ?year=2026&month=4.",
            },
        )
    settings = get_settings()
    return build_fir_intelligence(
        db,
        company_id,
        filter_year=year,
        filter_month=month,
        qty_reliable_since=settings.fir_intelligence_qty_reliable_since,
    )


@router.get("/pricing-modules", response_model=list[ModulePricingPublicOut])
def admin_list_pricing_modules(
    _: PlatformAdmin = Depends(get_platform_admin),
    db: Session = Depends(get_db_session),
):
    rows = list_all_pricing_rows(db)
    return [ModulePricingPublicOut.model_validate(r) for r in rows]


@router.patch("/pricing-modules/{module_name}", response_model=ModulePricingPublicOut)
def admin_patch_pricing_module(
    module_name: str,
    body: ModulePricingPatch,
    _: PlatformAdmin = Depends(get_platform_admin),
    db: Session = Depends(get_db_session),
):
    row = db.execute(select(ModulePricing).where(ModulePricing.module_name == module_name)).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Unknown module_name")
    patch = body.model_dump(exclude_unset=True)
    for k, v in patch.items():
        setattr(row, k, v)
    db.add(row)
    if "trial_days" in patch or "usage_limit" in patch:
        resync_qms_trials_after_pricing_change(db, row.module_name, row.trial_days, row.usage_limit)
    db.commit()
    db.refresh(row)
    return ModulePricingPublicOut.model_validate(row)
