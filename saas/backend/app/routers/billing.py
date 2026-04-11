"""Consolidated billing / usage overview for the Usage & billing page."""

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import get_settings
from app.dates import billing_today
from app.deps import get_company_for_user, get_current_company_user, get_db_session
from app.models import CompanyUser
from app.module_access import SLUG_TO_MODULE, access_state, actions_remaining_trial
from app.pricing_catalog import get_pricing_by_module_name
from app.schemas import BillingModuleRow, BillingOverviewResponse
from app.subscription_logic import (
    can_access_fir_workspace,
    can_create_invoice,
    count_combined_usage_this_month,
    count_fir_reports_this_month,
    plan_invoice_limit,
    subscription_is_active,
    trial_is_valid,
)

router = APIRouter(prefix="/api/billing", tags=["billing"])

_QMS_NAMES: list[tuple[str, str]] = [
    (slug, mname) for slug, mname in sorted(SLUG_TO_MODULE.items(), key=lambda x: x[1])
]


def _company_status(company, today: date) -> str:
    if subscription_is_active(company, today):
        return "Active"
    if trial_is_valid(company, today):
        return "Trial"
    return "Expired"


def _fir_module_status(company, today: date, enable_sub: bool) -> str:
    _ = enable_sub # FIR workspace always gated; label matches access only
    if trial_is_valid(company, today):
        return "Trial"
    if subscription_is_active(company, today):
        return "Active"
    return "Not Subscribed"


@router.get("/overview", response_model=BillingOverviewResponse)
def billing_overview(
    user: CompanyUser = Depends(get_current_company_user),
    db: Session = Depends(get_db_session),
):
    settings = get_settings()
    company = get_company_for_user(user, db)
    today = billing_today()
    utc = today

    inv_combined = count_combined_usage_this_month(db, company.id, today)
    fir_only = count_fir_reports_this_month(db, company.id, today)
    cap = plan_invoice_limit(db, company.plan_type)
    remaining_cap = None if cap is None else max(0, cap - inv_combined)

    ok, sub_msg = can_create_invoice(db, company, enable_subscription=settings.enable_subscription)
    can_ws = can_access_fir_workspace(
        company, enable_subscription=settings.enable_subscription, today=today
    )

    modules: list[BillingModuleRow] = [
        BillingModuleRow(
            module_key="fir",
            display_name="FIR Automation",
            subscription_status=_fir_module_status(company, today, settings.enable_subscription),
            reports_this_month=fir_only,
            combined_usage_this_month=inv_combined,
            usage_limit=cap,
            remaining=remaining_cap,
        )
    ]

    for _slug, mname in _QMS_NAMES:
        pr = get_pricing_by_module_name(db, mname)
        display = pr.display_name if pr else mname.replace("_", " ").title()
        access, trial, _sub, _msg = access_state(db, user.id, mname, today=utc, ensure_trial=False)
        if access == "full":
            modules.append(
                BillingModuleRow(
                    module_key=mname,
                    display_name=display,
                    subscription_status="Active",
                    usage_limit=None,
                    remaining=None,
                )
            )
        elif access == "trial" and trial:
            modules.append(
                BillingModuleRow(
                    module_key=mname,
                    display_name=display,
                    subscription_status="Trial",
                    trial_actions_used=trial.actions_used,
                    trial_actions_limit=trial.usage_limit,
                    trial_actions_remaining=actions_remaining_trial(trial),
                )
            )
        else:
            tlim = pr.usage_limit if pr else 5
            modules.append(
                BillingModuleRow(
                    module_key=mname,
                    display_name=display,
                    subscription_status="Not Subscribed",
                    trial_actions_used=0,
                    trial_actions_limit=tlim,
                    trial_actions_remaining=None,
                )
            )

    return BillingOverviewResponse(
        company_name=company.company_name,
        vendor_code=company.vendor_code,
        plan_name=str(company.plan_type).replace("_", " ").title(),
        enable_subscription=settings.enable_subscription,
        company_status=_company_status(company, today),
        trial_end_date=company.trial_end_date,
        subscription_start=company.subscription_start,
        subscription_end=company.subscription_end,
        modules=modules,
        can_access_fir_workspace=can_ws,
        subscription_message=None if ok else sub_msg,
    )
