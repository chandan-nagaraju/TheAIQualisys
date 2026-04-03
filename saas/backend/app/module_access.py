"""Trial + subscription gating for QMS modules (non-FIR)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ModuleSubscription, ModuleTrial
from app.pricing_catalog import qms_trial_defaults

# URL slug -> stored module_name
SLUG_TO_MODULE: dict[str, str] = {
    "drawings": "drawings_directory",
    "rc2a": "rc2a",
    "ppap": "ppap",
    "iatf": "iatf_documentation",
}

MODULE_TO_SLUG: dict[str, str] = {v: k for k, v in SLUG_TO_MODULE.items()}


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


def resolve_module_slug(slug: str) -> str | None:
    return SLUG_TO_MODULE.get(slug.strip().lower())


def active_subscription(db: Session, user_id: int, module_name: str, today: date) -> ModuleSubscription | None:
    row = db.execute(
        select(ModuleSubscription).where(
            ModuleSubscription.user_id == user_id,
            ModuleSubscription.module_name == module_name,
            ModuleSubscription.status == "active",
        )
    ).scalar_one_or_none()
    if not row:
        return None
    if today > row.end_date:
        return None
    if today < row.start_date:
        return None
    return row


def get_trial(db: Session, user_id: int, module_name: str) -> ModuleTrial | None:
    return db.execute(
        select(ModuleTrial).where(ModuleTrial.user_id == user_id, ModuleTrial.module_name == module_name)
    ).scalar_one_or_none()


def ensure_trial_row(db: Session, user_id: int, module_name: str, today: date) -> ModuleTrial:
    existing = get_trial(db, user_id, module_name)
    if existing:
        return existing
    trial_days, usage_limit = qms_trial_defaults(db, module_name)
    row = ModuleTrial(
        user_id=user_id,
        module_name=module_name,
        trial_start=today,
        trial_end=today + timedelta(days=trial_days),
        usage_limit=usage_limit,
        actions_used=0,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def trial_is_usable(trial: ModuleTrial, today: date) -> bool:
    if today > trial.trial_end:
        return False
    if trial.actions_used >= trial.usage_limit:
        return False
    return True


def days_remaining_trial(trial: ModuleTrial, today: date) -> int:
    return max(0, (trial.trial_end - today).days)


def actions_remaining_trial(trial: ModuleTrial) -> int:
    return max(0, trial.usage_limit - trial.actions_used)


def access_state(
    db: Session,
    user_id: int,
    module_name: str,
    *,
    today: date | None = None,
    ensure_trial: bool = False,
) -> tuple[str, ModuleTrial | None, ModuleSubscription | None, str | None]:
    """
    Returns (access, trial_row_or_none, sub_row_or_none, message).
    access is 'full' | 'trial' | 'denied'.
    When ensure_trial is True and no subscription, creates trial row if missing.
    """
    today = today or utc_today()
    sub = active_subscription(db, user_id, module_name, today)
    if sub:
        return "full", None, sub, None

    trial = get_trial(db, user_id, module_name)
    if trial is None:
        if not ensure_trial:
            return "denied", None, None, None
        trial = ensure_trial_row(db, user_id, module_name, today)

    if trial_is_usable(trial, today):
        return "trial", trial, None, None

    return (
        "denied",
        trial,
        None,
        "Your trial has ended. Please enroll to continue using this module.",
    )
