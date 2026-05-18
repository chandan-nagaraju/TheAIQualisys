"""Secured HTTP cron endpoints (invoke from Railway scheduler, GitHub Actions, etc.)."""

from __future__ import annotations

import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.dates import billing_today
from app.deps import get_db_session
from app.email_util import is_email_configured, send_subscription_expiring_email
from app.models import Company, CompanyUser
from app.subscription_logic import (
    count_fir_reports_in_subscription_window,
    subscription_is_active,
    subscription_period_start_for_reports,
)

router = APIRouter(prefix="/cron", tags=["cron"])
logger = logging.getLogger(__name__)


@router.post("/send-subscription-expiry-reminders")
def send_subscription_expiry_reminders(
    db: Session = Depends(get_db_session),
    x_cron_secret: str | None = Header(None, alias="X-Cron-Secret"),
):
    """
    Email company users when subscription_end matches the configured offset from today.

    Schedule daily (UTC, same basis as billing_today). Set CRON_SECRET in the API env and call:

        curl -X POST "$API/api/cron/send-subscription-expiry-reminders" -H "X-Cron-Secret: $CRON_SECRET"

    SUBSCRIPTION_EXPIRY_REMINDER_DAYS_BEFORE=0 → send on the last day (subscription_end == today).
    =1 → send when subscription ends tomorrow (one calendar day before end).
    """
    settings = get_settings()
    if not settings.cron_secret or (x_cron_secret or "").strip() != settings.cron_secret.strip():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing cron secret")
    if not is_email_configured(settings):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email not configured (RESEND_API_KEY or SMTP + EMAIL_FROM).",
        )

    today = billing_today()
    offset = max(0, settings.subscription_expiry_reminder_days_before)
    target_end = today + timedelta(days=offset)

    companies = (
        db.execute(select(Company).where(Company.subscription_end == target_end).order_by(Company.id))
        .scalars()
        .all()
    )
    billing_url = f"{settings.public_app_url.rstrip('/')}/dashboard/billing"
    companies_notified = 0
    emails_sent = 0
    errors: list[str] = []

    for company in companies:
        if company.subscription_expiry_reminder_sent_for_end == company.subscription_end:
            continue
        if not subscription_is_active(company, today):
            continue

        period_start = subscription_period_start_for_reports(company)
        report_count = count_fir_reports_in_subscription_window(db, company.id, period_start, today)
        users = (
            db.execute(
                select(CompanyUser)
                .where(CompanyUser.company_id == company.id, CompanyUser.is_blocked == 0)
                .order_by(CompanyUser.id)
            )
            .scalars()
            .all()
        )
        if not users:
            continue

        sub_end_s = company.subscription_end.isoformat() if company.subscription_end else ""
        period_s = period_start.isoformat()
        company_ok = True
        for u in users:
            try:
                send_subscription_expiring_email(
                    settings,
                    u.email,
                    company_name=company.company_name,
                    subscription_end=sub_end_s,
                    reports_in_period=report_count,
                    period_started_on=period_s,
                    billing_url=billing_url,
                )
                emails_sent += 1
            except Exception as exc:
                company_ok = False
                msg = f"company_id={company.id} user={u.email!s}: {exc!s}"
                errors.append(msg)
                logger.warning("subscription expiry email failed: %s", msg, exc_info=True)

        if company_ok:
            company.subscription_expiry_reminder_sent_for_end = company.subscription_end
            db.add(company)
            companies_notified += 1

    db.commit()
    return {
        "ok": True,
        "today": today.isoformat(),
        "target_subscription_end": target_end.isoformat(),
        "days_before_end": offset,
        "companies_notified": companies_notified,
        "emails_sent": emails_sent,
        "errors": errors,
    }
