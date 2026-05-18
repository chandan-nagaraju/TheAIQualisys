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
from app.subscription_logic import count_fir_reports_this_month

router = APIRouter(prefix="/cron", tags=["cron"])
logger = logging.getLogger(__name__)

# Bit 1 = morning reminder sent; bit 2 = evening reminder sent.
_MASK_MORNING = 1
_MASK_EVENING = 2
# First N minutes of each scheduled local hour (cron should hit at least once inside each window).
_SLOT_GRACE_MINUTES = 5


def _build_reminder_slots(
    *,
    force: bool,
    in_morning_slot: bool,
    in_evening_slot: bool,
    mask: int,
    expires_today: bool,
    expired: bool,
    morning_hour: int,
    evening_hour: int,
) -> list[tuple[str, int]]:
    slots: list[tuple[str, int]] = []
    if force:
        if (mask & _MASK_MORNING) == 0 and (expires_today or expired):
            slots.append(("morning", _MASK_MORNING))
        if (mask & _MASK_EVENING) == 0 and expires_today and evening_hour != morning_hour:
            slots.append(("evening", _MASK_EVENING))
        return slots

    if in_morning_slot and (mask & _MASK_MORNING) == 0 and (expires_today or expired):
        slots.append(("morning", _MASK_MORNING))
    if in_evening_slot and (mask & _MASK_EVENING) == 0 and expires_today and evening_hour != morning_hour:
        slots.append(("evening", _MASK_EVENING))
    return slots


@router.post("/send-subscription-expiry-reminders")
def send_subscription_expiry_reminders(
    db: Session = Depends(get_db_session),
    x_cron_secret: str | None = Header(None, alias="X-Cron-Secret"),
    force: bool = Query(
        False,
        description="If true, send pending allowed slots now (still requires X-Cron-Secret).",
    ),
):
    """
    **Last day** (`subscription_end == today` in ``SUBSCRIPTION_REMINDER_TIMEZONE``): morning + evening slots.

    **After expiry** (`subscription_end < today_local`): morning only, once per local day, until renewal.

    **Renewed** (`subscription_end > today_local`): excluded — no emails.

    Same email template for all cases. Schedule HTTP often enough to hit minutes 0–4 of morning/evening hours,
    or use ``?force=true`` for catch-up.

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
            select(Company)
            .where(
                Company.subscription_end.is_not(None),
                Company.subscription_end <= today_local,
            )
            .order_by(Company.id),
        )
        .scalars()
        .all()
    )
    billing_url = f"{settings.public_app_url.rstrip('/')}/dashboard/billing"
    companies_touched = 0
    emails_sent = 0
    errors: list[str] = []

    for company in companies:
        sub_end = company.subscription_end
        assert sub_end is not None

        expires_today = sub_end == today_local
        expired = sub_end < today_local

        company_dirty = False
        if company.subscription_expiry_reminder_date != today_local:
            company.subscription_expiry_reminder_mask = 0
            company.subscription_expiry_reminder_date = today_local
            company_dirty = True

        mask = company.subscription_expiry_reminder_mask
        mask_before = mask

        slots = _build_reminder_slots(
            force=force,
            in_morning_slot=in_morning_slot,
            in_evening_slot=in_evening_slot,
            mask=mask,
            expires_today=expires_today,
            expired=expired,
            morning_hour=mh,
            evening_hour=eh,
        )

        if not slots:
            if company_dirty:
                db.add(company)
                companies_touched += 1
            continue

        fir_count = count_fir_reports_this_month(db, company.id, today_local)
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
            if company_dirty:
                db.add(company)
                companies_touched += 1
            continue

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
                company_dirty = True

        if company_dirty or mask != mask_before:
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
