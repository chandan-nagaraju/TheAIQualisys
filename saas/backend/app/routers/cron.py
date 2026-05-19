"""Secured HTTP cron endpoints (invoke from Railway scheduler, GitHub Actions, etc.)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.deps import get_db_session
from app.email_util import is_email_configured
from app.subscription_reminder_runner import run_subscription_expiry_reminders

router = APIRouter(prefix="/cron", tags=["cron"])


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

    The API process also runs the same logic every minute when
    ``ENABLE_AUTOMATIC_SUBSCRIPTION_REMINDERS`` is true (default). Use this endpoint for
    manual catch-up with ``?force=true``.

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
        return run_subscription_expiry_reminders(db, settings, force=force)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
