"""Run subscription expiry reminder emails (HTTP cron and in-process scheduler)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.email_util import is_email_configured, send_subscription_expiring_email, send_trial_ending_email
from app.models import Company, CompanyUser
from app.subscription_logic import count_fir_reports_this_month, subscription_is_active

logger = logging.getLogger(__name__)

_MASK_MORNING = 1
_MASK_EVENING = 2
# Any minute within the scheduled local hour counts (daily scheduler wakes once at :00; masks prevent duplicates).
_SLOT_GRACE_MINUTES = 60
# Email trial tenants this many days before trial_end (inclusive of last day).
_TRIAL_REMINDER_LEAD_DAYS = 2
# One morning catch-up the day after trial_end if they have not subscribed.
_TRIAL_REMINDER_AFTER_END_DAYS = 1


def company_due_for_trial_reminder(company: Company, today) -> bool:
    """True when the FIR company trial is ending soon or just ended, and they are not on a paid plan."""
    if subscription_is_active(company, today):
        return False
    te = company.trial_end_date
    if te is None:
        return False
    days = (te - today).days
    return -_TRIAL_REMINDER_AFTER_END_DAYS <= days <= _TRIAL_REMINDER_LEAD_DAYS


def _build_reminder_slots(
    *,
    force: bool,
    in_morning_slot: bool,
    in_evening_slot: bool,
    mask: int,
    expires_today: bool,
    expired: bool,
    ending_soon: bool,
    morning_hour: int,
    evening_hour: int,
) -> list[tuple[str, int]]:
    due_morning = expires_today or expired or ending_soon
    slots: list[tuple[str, int]] = []
    if force:
        if (mask & _MASK_MORNING) == 0 and due_morning:
            slots.append(("morning", _MASK_MORNING))
        if (mask & _MASK_EVENING) == 0 and expires_today and evening_hour != morning_hour:
            slots.append(("evening", _MASK_EVENING))
        return slots

    if in_morning_slot and (mask & _MASK_MORNING) == 0 and due_morning:
        slots.append(("morning", _MASK_MORNING))
    if in_evening_slot and (mask & _MASK_EVENING) == 0 and expires_today and evening_hour != morning_hour:
        slots.append(("evening", _MASK_EVENING))
    return slots


def run_subscription_expiry_reminders(db: Session, settings: Settings, *, force: bool = False) -> dict:
    """
    Send reminder emails:

    * Paid: ``subscription_end <= today`` (existing last-day / after-expiry).
    * Trial: ``trial_end_date`` in [today-1, today+2] while not on a paid subscription.

    When ``force`` is False, only runs during the first ``_SLOT_GRACE_MINUTES`` minutes of
    morning_hour / evening_hour in ``settings.subscription_reminder_timezone``.
    """
    if not is_email_configured(settings):
        raise RuntimeError("Email not configured (RESEND_API_KEY or SMTP + EMAIL_FROM).")

    try:
        tz = ZoneInfo(settings.subscription_reminder_timezone)
    except Exception as exc:
        raise ValueError(
            f"Invalid SUBSCRIPTION_REMINDER_TIMEZONE: {settings.subscription_reminder_timezone!r}"
        ) from exc

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
                f"No send window: need a run during local hour {mh} or {eh} "
                f"({settings.subscription_reminder_timezone}), or use force=True for catch-up."
            ),
            "local_time": now_local.isoformat(),
            "today_local": today_local.isoformat(),
            "companies_touched": 0,
            "emails_sent": 0,
            "errors": [],
        }

    trial_lo = today_local - timedelta(days=_TRIAL_REMINDER_AFTER_END_DAYS)
    trial_hi = today_local + timedelta(days=_TRIAL_REMINDER_LEAD_DAYS)
    companies = (
        db.execute(
            select(Company)
            .where(
                or_(
                    and_(
                        Company.subscription_end.is_not(None),
                        Company.subscription_end <= today_local,
                    ),
                    and_(
                        Company.trial_end_date.is_not(None),
                        Company.trial_end_date >= trial_lo,
                        Company.trial_end_date <= trial_hi,
                    ),
                )
            )
            .order_by(Company.id),
        )
        .scalars()
        .all()
    )
    billing_url = f"{settings.public_app_url.rstrip('/')}/dashboard/billing"
    subscribe_url = f"{settings.public_app_url.rstrip('/')}/workspace/pricing"
    companies_touched = 0
    emails_sent = 0
    errors: list[str] = []

    for company in companies:
        paid_end = company.subscription_end
        use_paid = paid_end is not None and paid_end <= today_local
        use_trial = (not use_paid) and company_due_for_trial_reminder(company, today_local)
        if not use_paid and not use_trial:
            continue

        if use_paid:
            end_date = paid_end
            assert end_date is not None
        else:
            end_date = company.trial_end_date
            assert end_date is not None

        expires_today = end_date == today_local
        expired = end_date < today_local
        ending_soon = end_date > today_local

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
            ending_soon=ending_soon,
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
                    if use_trial:
                        send_trial_ending_email(
                            settings,
                            u.email,
                            company_name=company.company_name,
                            trial_end_date=end_date,
                            subscribe_url=subscribe_url,
                            already_ended=expired,
                        )
                    else:
                        send_subscription_expiring_email(
                            settings,
                            u.email,
                            company_name=company.company_name,
                            subscription_end_date=end_date,
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
