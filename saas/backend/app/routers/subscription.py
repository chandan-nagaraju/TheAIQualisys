from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.dates import billing_today
from app.deps import get_company_for_user, get_current_company_user, get_db_session
from app.models import CompanyUser
from app.pricing_catalog import list_fir_plan_rows
from app.schemas import CompanyOut, PlanInfo, SubscriptionStatusResponse, UpgradeInfoResponse
from app.subscription_logic import (
    can_access_fir_workspace,
    can_create_invoice,
    can_record_fir_reports,
    count_combined_usage_this_month,
    count_fir_reports_this_month,
    count_invoices_this_month,
    plan_invoice_limit,
    subscription_days_remaining_company,
    subscription_is_active,
    trial_days_remaining_company,
    trial_is_valid,
)

router = APIRouter(prefix="/subscription", tags=["subscription"])


def _fallback_plans() -> list[PlanInfo]:
    return [
        PlanInfo(plan_type="basic", name="Basic", price_inr=2799, min_invoices=0, max_invoices=1000),
        PlanInfo(plan_type="pro", name="Pro", price_inr=4599, min_invoices=1001, max_invoices=2000),
        PlanInfo(
            plan_type="enterprise",
            name="Enterprise",
            price_inr=6599,
            min_invoices=2001,
            max_invoices=None,
            highlight="Best for growing companies",
        ),
    ]


@router.get("/plans", response_model=list[PlanInfo])
def list_plans(db: Session = Depends(get_db_session)):
    rows = list_fir_plan_rows(db)
    if not rows:
        return _fallback_plans()
    return [
        PlanInfo(
            plan_type=r.fir_plan_type or "basic",
            name=r.display_name,
            price_inr=r.monthly_price,
            min_invoices=r.invoice_min or 0,
            max_invoices=r.invoice_max,
            highlight=r.highlight,
        )
        for r in rows
        if r.fir_plan_type
    ]


@router.get("/status", response_model=SubscriptionStatusResponse)
def subscription_status(
    user: CompanyUser = Depends(get_current_company_user),
    db: Session = Depends(get_db_session),
):
    settings = get_settings()
    company = get_company_for_user(user, db)
    today = billing_today()
    inv = count_invoices_this_month(db, company.id, today)
    fir = count_fir_reports_this_month(db, company.id, today)
    usage = count_combined_usage_this_month(db, company.id, today)
    limit = plan_invoice_limit(db, company.plan_type)
    ok, _ = can_create_invoice(db, company, enable_subscription=settings.enable_subscription)
    ok_fir, _ = can_record_fir_reports(
        db, company, n=1, enable_subscription=settings.enable_subscription, today=today
    )

    return SubscriptionStatusResponse(
        enable_subscription=settings.enable_subscription,
        company=CompanyOut.model_validate(company),
        invoices_this_month=inv,
        fir_reports_this_month=fir,
        usage_this_month=usage,
        invoice_limit=limit,
        can_create_invoice=ok,
        can_record_fir_report=ok_fir,
        trial_active=trial_is_valid(company, today),
        subscription_active=subscription_is_active(company, today),
        can_access_fir_workspace=can_access_fir_workspace(
            company, enable_subscription=settings.enable_subscription, today=today
        ),
        trial_days_remaining=trial_days_remaining_company(company, today),
        subscription_days_remaining=subscription_days_remaining_company(company, today),
    )


@router.get("/upgrade-info", response_model=UpgradeInfoResponse)
def upgrade_info():
    settings = get_settings()
    msg = settings.whatsapp_message_template.format(upi_id=settings.upi_id)
    # Accept common admin formats like "+91 78920 07580" or "+91-78920-07580".
    # wa.me requires digits only; any punctuation causes WhatsApp 404.
    phone = "".join(ch for ch in settings.whatsapp_number if ch.isdigit())
    if not phone:
        raise HTTPException(
            status_code=503,
            detail="Upgrade contact is not configured. Please set WHATSAPP_NUMBER on the backend.",
        )
    if len(phone) < 10:
        raise HTTPException(
            status_code=503,
            detail="Upgrade contact number is invalid. WHATSAPP_NUMBER must contain at least 10 digits.",
        )
    url = f"https://wa.me/{phone}?text={quote(msg)}"
    return UpgradeInfoResponse(upi_id=settings.upi_id, whatsapp_url=url, message=msg)
