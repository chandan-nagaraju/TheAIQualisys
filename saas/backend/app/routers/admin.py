from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.deps import get_db_session, get_platform_admin
from app.fir_analytics import build_fir_intelligence
from app.models import Company, CompanyUser, Customer, InvoiceV2, ModulePricing, PlanType, PlatformAdmin, SubscriptionStatus
from app.pricing_catalog import list_all_pricing_rows
from app.schemas import (
    AdminCompanyPatch,
    AdminCompanySummary,
    AdminDashboardResponse,
    AdminFirCustomerRow,
    AdminLoginRequest,
    AdminTenantUserRow,
    CompanyOut,
    ModulePricingPatch,
    ModulePricingPublicOut,
    TokenResponse,
)
from app.security import create_access_token, create_admin_token, hash_password, verify_password
from app.subscription_logic import count_fir_reports_this_month, count_invoices_this_month

router = APIRouter(prefix="/admin", tags=["admin"])


def _company_out(c: Company) -> CompanyOut:
    return CompanyOut.model_validate(c)


@router.post("/login", response_model=TokenResponse)
def admin_login(body: AdminLoginRequest, db: Session = Depends(get_db_session)):
    admin = db.execute(select(PlatformAdmin).where(PlatformAdmin.email == str(body.email).lower())).scalar_one_or_none()
    if not admin or not verify_password(body.password, admin.password_hash):
        raise HTTPException(status_code=401, detail="Invalid admin credentials")
    token = create_admin_token(str(admin.id))
    return TokenResponse(access_token=token)


@router.get("/dashboard", response_model=AdminDashboardResponse)
def admin_dashboard(
    _: PlatformAdmin = Depends(get_platform_admin),
    db: Session = Depends(get_db_session),
):
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
    return [
        AdminTenantUserRow(
            user_id=u.id,
            email=u.email,
            name=u.name,
            created_at=u.created_at,
            company_id=c.id,
            company_name=c.company_name,
            company_vendor_code=c.vendor_code,
            plan_type=c.plan_type,
            subscription_status=c.subscription_status,
        )
        for u, c in rows
    ]


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
    today = date.today()
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

    today = date.today()

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

    else:
        raise HTTPException(status_code=400, detail="Unknown action")

    db.commit()
    db.refresh(c)
    return _company_out(c)


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
    today = date.today()
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


@router.get("/companies/{company_id}/fir-intelligence")
def company_fir_intelligence(
    company_id: int,
    _: PlatformAdmin = Depends(get_platform_admin),
    db: Session = Depends(get_db_session),
):
    c = db.get(Company, company_id)
    if not c:
        raise HTTPException(status_code=404, detail="Company not found")
    return build_fir_intelligence(db, company_id)


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
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    db.add(row)
    db.commit()
    db.refresh(row)
    return ModulePricingPublicOut.model_validate(row)
