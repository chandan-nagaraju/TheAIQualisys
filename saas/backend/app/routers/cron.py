"""Secured HTTP cron endpoints (invoke from Railway scheduler, GitHub Actions, etc.)."""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.deps import get_db_session
from app.email_util import is_email_configured, send_subscription_expiring_email
from app.models import Company, CompanyUser
from app.subscription_logic import count_fir_reports_this_month, subscription_is_active

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
    force: bool = Query(
        False,
        description="If true, send any pending slots now (still requires X-Cron-Secret). For manual catch-up.",
    ),
):
    """
    On the last calendar day of ``subscription_end`` (in ``SUBSCRIPTION_REMINDER_TIMEZONE``), send email
    at **morning_hour** and **evening_hour**: first successful cron invocation in minutes **0–4** of
    each of those hours (defaults **9** and **17**).

    Schedule HTTP **every 1–5 minutes** so a call lands inside **09:00–09:04** and **17:00–17:04**
    (local). Set ``SUBSCRIPTION_REMINDER_TIMEZONE`` (e.g. ``Asia/Kolkata``).

    **Manual catch-up:** ``POST ...?force=true`` with the same secret sends **pending** morning and/or
    evening emails for today's expiries (no clock window).

        curl -X POST "$API/api/cron/send-subscription-expiry-reminders" -H "X-Cron-Secret: $CRON_SECRET"
        curl -X POST "$API/api/cron/send-subscription-expiry-reminders?force=true" -H "X-Cron-Secret: $CRON_SECRET"
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

    if not force and not in_morning_slot and not in_evening_slot:
        db.commit()
        return {
            "ok": True,
            "skipped": True,
            "forced": False,
            "reason": (
                f"No send window: need a cron hit in minutes 0–{_SLOT_GRACE_MINUTES - 1} of hour {mh} or {eh} "
                f"({settings.subscription_reminder_timezone}), or use ?force=true for catch-up."
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
        slots: list[tuple[str, int]] = []
        if force:
            if eh == mh:
                if (mask & _MASK_MORNING) == 0:
                    slots.append(("morning", _MASK_MORNING))
            else:
                if (mask & _MASK_MORNING) == 0:
                    slots.append(("morning", _MASK_MORNING))
                if (mask & _MASK_EVENING) == 0:
                    slots.append(("evening", _MASK_EVENING))
        else:
            if in_morning_slot and (mask & _MASK_MORNING) == 0:
                slots.append(("morning", _MASK_MORNING))
            elif in_evening_slot and (mask & _MASK_EVENING) == 0:
                slots.append(("evening", _MASK_EVENING))

        if not slots:
            continue

        fir_count = count_fir_reports_this_month(db, company.id, today_local)
        sub_end = company.subscription_end
        assert sub_end is not None
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

        mask_before = mask

        for slot, bit in slots:
            slot_ok = True
            for u in users:
                try:
                    send_subscription_expiring_email(
                        settings,
                        u.email,
                        company_name=company.company_name,
                        subscription_end_date=sub_end,
                        fir_count=fir_count,
                        billing_url=billing_url,
                    )
                    emails_sent += 1
                except Exception as exc:
                    slot_ok = False
                    msg = f"company_id={company.id} user={u.email!s} slot={slot}: {exc!s}"
                    errors.append(msg)
                    logger.warning("subscription expiry email failed: %s", msg, exc_info=True)

            if slot_ok:
                mask |= bit
                company.subscription_expiry_reminder_mask = mask

        if mask != mask_before:
            db.add(company)
            companies_touched += 1

    db.commit()
    return {
        "ok": True,
        "skipped": False,
        "forced": force,
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
