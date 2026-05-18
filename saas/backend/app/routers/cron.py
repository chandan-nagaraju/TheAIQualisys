"""Secured HTTP cron endpoints (invoke from Railway scheduler, GitHub Actions, etc.)."""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
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

# Bit 0 = morning hour slot sent; bit 1 = evening hour slot sent.
_MASK_MORNING = 1
_MASK_EVENING = 2
# Treat "9:00" / "17:00" as the first N minutes of that local hour (cron should run at least once in each window).
_SLOT_GRACE_MINUTES = 5


@router.post("/send-subscription-expiry-reminders")
def send_subscription_expiry_reminders(
    db: Session = Depends(get_db_session),
    x_cron_secret: str | None = Header(None, alias="X-Cron-Secret"),
):
    """
    On the last calendar day of ``subscription_end`` (in ``SUBSCRIPTION_REMINDER_TIMEZONE``), send email
    at **morning_hour** and **evening_hour**: first successful cron invocation in minutes **0–4** of
    each of those hours (defaults **9** and **17**).

    Schedule HTTP **every 1–5 minutes** so a call lands inside **09:00–09:04** and **17:00–17:04**
    (local). Set ``SUBSCRIPTION_REMINDER_TIMEZONE`` (e.g. ``Asia/Kolkata``).

        curl -X POST "$API/api/cron/send-subscription-expiry-reminders" -H "X-Cron-Secret: $CRON_SECRET"
    """
    settings = get_settings()
    if not settings.cron_secret or (x_cron_secret or "").strip() != settings.cron_secret.strip():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing cron secret")
    if not is_email_configured(settings):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email not configured (RESEND_API_KEY or SMTP + EMAIL_FROM).",
        )

    try:
        tz = ZoneInfo(settings.subscription_reminder_timezone)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Invalid SUBSCRIPTION_REMINDER_TIMEZONE: {settings.subscription_reminder_timezone!r}",
        ) from None

    now_local = datetime.now(tz)
    today_local = now_local.date()
    h, m = now_local.hour, now_local.minute
    mh = settings.subscription_reminder_morning_hour
    eh = settings.subscription_reminder_evening_hour

    in_morning_slot = h == mh and m < _SLOT_GRACE_MINUTES
    in_evening_slot = h == eh and m < _SLOT_GRACE_MINUTES and eh != mh

    if not in_morning_slot and not in_evening_slot:
        db.commit()
        return {
            "ok": True,
            "skipped": True,
            "reason": (
                f"No send window: need a cron hit in minutes 0–{_SLOT_GRACE_MINUTES - 1} of hour {mh} or {eh} "
                f"({settings.subscription_reminder_timezone})"
            ),
            "local_time": now_local.isoformat(),
            "today_local": today_local.isoformat(),
            "companies_touched": 0,
            "emails_sent": 0,
            "errors": [],
        }

    companies = (
        db.execute(
            select(Company).where(Company.subscription_end == today_local).order_by(Company.id),
        )
        .scalars()
        .all()
    )
    billing_url = f"{settings.public_app_url.rstrip('/')}/dashboard/billing"
    companies_touched = 0
    emails_sent = 0
    errors: list[str] = []

    for company in companies:
        if not subscription_is_active(company, today_local):
            continue

        if company.subscription_expiry_reminder_sent_for_end != company.subscription_end:
            company.subscription_expiry_reminder_mask = 0
            company.subscription_expiry_reminder_sent_for_end = company.subscription_end

        mask = company.subscription_expiry_reminder_mask
        slot: str | None = None
        bit = 0
        if in_morning_slot and (mask & _MASK_MORNING) == 0:
            slot = "morning"
            bit = _MASK_MORNING
        elif in_evening_slot and (mask & _MASK_EVENING) == 0:
            slot = "evening"
            bit = _MASK_EVENING

        if slot is None:
            continue

        period_start = subscription_period_start_for_reports(company)
        report_count = count_fir_reports_in_subscription_window(db, company.id, period_start, today_local)
        users = (
            db.execute(
                select(CompanyUser)
                .where(CompanyUser.company_id == company.id, CompanyUser.is_blocked == 0)
                .order_by(CompanyUser.id),
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
                    reminder_slot=slot,
                    morning_hour=mh,
                    evening_hour=eh,
                )
                emails_sent += 1
            except Exception as exc:
                company_ok = False
                msg = f"company_id={company.id} user={u.email!s}: {exc!s}"
                errors.append(msg)
                logger.warning("subscription expiry email failed: %s", msg, exc_info=True)

        if company_ok:
            company.subscription_expiry_reminder_mask = mask | bit
            db.add(company)
            companies_touched += 1

    db.commit()
    return {
        "ok": True,
        "skipped": False,
        "timezone": settings.subscription_reminder_timezone,
        "local_time": now_local.isoformat(),
        "today_local": today_local.isoformat(),
        "morning_hour": mh,
        "evening_hour": eh,
        "in_morning_window": in_morning_slot,
        "in_evening_window": in_evening_slot,
        "companies_touched": companies_touched,
        "emails_sent": emails_sent,
        "errors": errors,
    }
