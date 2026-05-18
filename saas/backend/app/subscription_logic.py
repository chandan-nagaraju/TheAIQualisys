from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Company, FirReportEvent, InvoiceV2, SubscriptionStatus
from app.pricing_catalog import invoice_cap_for_plan

FIR_WORKSPACE_FORBIDDEN_CODE = "FIR_WORKSPACE_FORBIDDEN"
FIR_WORKSPACE_FORBIDDEN_MESSAGE = (
    "Trial ended or subscription inactive. Open Billing or Upgrade to continue; "
    "the FIR workspace is unavailable until you have an active trial or paid plan."
)


def plan_invoice_limit(db: Session, plan_type: str) -> int | None:
    """Monthly combined usage cap (v2 invoices + FIR reports); None = unlimited."""
    return invoice_cap_for_plan(db, plan_type)


def month_bounds_utc(d: date) -> tuple[datetime, datetime]:
    start = datetime(d.year, d.month, 1, tzinfo=timezone.utc)
    last_day = monthrange(d.year, d.month)[1]
    end = datetime(d.year, d.month, last_day, 23, 59, 59, 999999, tzinfo=timezone.utc)
    return start, end


def count_invoices_this_month(db: Session, company_id: int, today: date | None = None) -> int:
    today = today or datetime.now(timezone.utc).date()
    start, end = month_bounds_utc(today)
    q = select(func.count()).select_from(InvoiceV2).where(
        InvoiceV2.company_id == company_id,
        InvoiceV2.created_at >= start,
        InvoiceV2.created_at <= end,
    )
    return int(db.execute(q).scalar_one())


def count_fir_reports_this_month(db: Session, company_id: int, today: date | None = None) -> int:
    """FIR intelligence rows whose **invoice_date** falls in the same calendar month as ``today``.

    One row per invoice line ingested into ``fir_events``; the business month is the invoice date
    on the file (same basis as admin FIR charts and monthly slices), not ``created_at``.
    """
    today = today or datetime.now(timezone.utc).date()
    first = date(today.year, today.month, 1)
    last_day_num = monthrange(today.year, today.month)[1]
    last = date(today.year, today.month, last_day_num)
    q = select(func.count()).select_from(FirReportEvent).where(
        FirReportEvent.company_id == company_id,
        FirReportEvent.invoice_date >= first,
        FirReportEvent.invoice_date <= last,
    )
    return int(db.execute(q).scalar_one())


def count_combined_usage_this_month(db: Session, company_id: int, today: date | None = None) -> int:
    """Invoices (v2) + FIR report rows — both count toward the same monthly plan cap."""
    return count_invoices_this_month(db, company_id, today) + count_fir_reports_this_month(
        db, company_id, today
    )


def trial_is_valid(company: Company, today: date | None = None) -> bool:
    """True when today falls in the company's trial calendar window (independent of stored status)."""
    today = today or datetime.now(timezone.utc).date()
    return company.trial_start_date <= today <= company.trial_end_date


def trial_days_remaining_company(company: Company, today: date | None = None) -> int | None:
    """Calendar days left in company FIR trial window, or None if not in trial."""
    today = today or datetime.now(timezone.utc).date()
    if not trial_is_valid(company, today):
        return None
    return max(0, (company.trial_end_date - today).days)


def subscription_is_active(company: Company, today: date | None = None) -> bool:
    """
    True when the company's paid subscription window covers `today` (calendar only).

    Do not require subscription_status == "active": billing flows sometimes leave
    status as "trial" until a job updates it, which incorrectly blocked FIR access
    between trial_end and subscription_end.
    """
    today = today or datetime.now(timezone.utc).date()
    if company.subscription_status == SubscriptionStatus.expired.value:
        return False
    if company.subscription_end is None:
        return False
    if today > company.subscription_end:
        return False
    if company.subscription_start is not None and today < company.subscription_start:
        return False
    return True


def sync_subscription_status_from_dates(company: Company, today: date | None = None) -> bool:
    """
    Set subscription_status from trial and subscription dates.
    Priority: trial window > paid window > expired.
    Returns True if the stored status was changed (caller may commit).
    """
    today = today or datetime.now(timezone.utc).date()
    if company.trial_start_date <= today <= company.trial_end_date:
        new_status = SubscriptionStatus.trial.value
    elif company.subscription_end is not None and today <= company.subscription_end and (
        company.subscription_start is None or today >= company.subscription_start
    ):
        new_status = SubscriptionStatus.active.value
    else:
        new_status = SubscriptionStatus.expired.value
    if company.subscription_status != new_status:
        company.subscription_status = new_status
        return True
    return False


def subscription_days_remaining_company(company: Company, today: date | None = None) -> int | None:
    """Days until subscription_end while subscription is active; None otherwise."""
    today = today or datetime.now(timezone.utc).date()
    if not subscription_is_active(company, today):
        return None
    if company.subscription_end is None:
        return None
    return max(0, (company.subscription_end - today).days)


def subscription_period_start_for_reports(company: Company) -> date:
    """
    First calendar day of the current paid window for "since subscription started" copy.
    Uses subscription_start when set; otherwise the day after trial end if a paid end date exists.
    """
    if company.subscription_start is not None:
        return company.subscription_start
    if company.subscription_end is not None:
        return company.trial_end_date + timedelta(days=1)
    return company.trial_start_date


def count_fir_reports_in_subscription_window(
    db: Session, company_id: int, period_start: date, until: date
) -> int:
    """Count FIR intelligence rows with invoice_date in [period_start, until] inclusive."""
    q = select(func.count()).select_from(FirReportEvent).where(
        FirReportEvent.company_id == company_id,
        FirReportEvent.invoice_date >= period_start,
        FirReportEvent.invoice_date <= until,
    )
    return int(db.execute(q).scalar_one())


def can_create_invoice(
    db: Session,
    company: Company,
    *,
    enable_subscription: bool,
    today: date | None = None,
) -> tuple[bool, str | None]:
    """
    Returns (allowed, error_message).
    When enable_subscription is False, always allow (feature flag off).
    """
    if not enable_subscription:
        return True, None

    today = today or datetime.now(timezone.utc).date()

    if trial_is_valid(company, today):
        return True, None

    if subscription_is_active(company, today):
        limit = plan_invoice_limit(db, company.plan_type)
        if limit is None:
            return True, None
        used = count_combined_usage_this_month(db, company.id, today)
        if used >= limit:
            return False, "Monthly usage limit reached (invoices + FIR reports). Please upgrade."
        return True, None

    # Expired trial and not active paid
    if company.subscription_status == SubscriptionStatus.expired.value:
        return False, "Subscription expired. Upgrade to create invoices."

    if company.subscription_status == SubscriptionStatus.trial.value and today > company.trial_end_date:
        return False, "Trial ended. Upgrade to create invoices."

    if company.subscription_status == SubscriptionStatus.active.value and not subscription_is_active(company, today):
        return False, "Subscription period ended. Please renew."

    return False, "Cannot create invoices with current subscription status."


def can_record_fir_reports(
    db: Session,
    company: Company,
    *,
    n: int,
    enable_subscription: bool,
    today: date | None = None,
) -> tuple[bool, str | None]:
    """Allow recording n new FIR report rows; same subscription gates as invoices (combined cap)."""
    if n < 0:
        return False, "Invalid report count"
    if not enable_subscription:
        return True, None

    today = today or datetime.now(timezone.utc).date()

    if trial_is_valid(company, today):
        return True, None

    if subscription_is_active(company, today):
        limit = plan_invoice_limit(db, company.plan_type)
        if limit is None:
            return True, None
        used = count_combined_usage_this_month(db, company.id, today)
        if used + n > limit:
            return False, "Monthly usage limit reached (invoices + FIR reports). Please upgrade."
        return True, None

    if company.subscription_status == SubscriptionStatus.expired.value:
        return False, "Subscription expired. Upgrade to generate FIR reports."

    if company.subscription_status == SubscriptionStatus.trial.value and today > company.trial_end_date:
        return False, "Trial ended. Upgrade to generate FIR reports."

    if company.subscription_status == SubscriptionStatus.active.value and not subscription_is_active(company, today):
        return False, "Subscription period ended. Please renew."

    return False, "Cannot record FIR reports with current subscription status."


def can_access_app(company: Company, *, enable_subscription: bool, today: date | None = None) -> bool:
    """Read access: trial valid, active subscription, or expired (view-only still allowed at route level)."""
    if not enable_subscription:
        return True
    today = today or datetime.now(timezone.utc).date()
    if trial_is_valid(company, today):
        return True
    if subscription_is_active(company, today):
        return True
    # Expired / post-trial: still allow login and read endpoints
    return True


def can_access_fir_workspace(
    company: Company,
    *,
    enable_subscription: bool,
    today: date | None = None,
    impersonated_by_admin: bool = False,
) -> bool:
    """
    FIR workspace (/api/app/*) — always requires an active company trial or paid subscription window.
    Company billing routes (v2 /me, /subscription/status, etc.) stay reachable via can_access_app.
    Platform admins impersonating a tenant always get workspace access for support.
    `enable_subscription` is kept for call-site compatibility; it does not bypass this gate.
    """
    _ = enable_subscription
    if impersonated_by_admin:
        return True
    today = today or datetime.now(timezone.utc).date()
    if trial_is_valid(company, today):
        return True
    if subscription_is_active(company, today):
        return True
    return False
