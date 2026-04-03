"""QMS module trial/subscription API (non-FIR)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.deps import get_current_company_user, get_db_session
from app.models import CompanyUser
from app.module_access import (
    SLUG_TO_MODULE,
    access_state,
    actions_remaining_trial,
    days_remaining_trial,
    resolve_module_slug,
    utc_today,
)
from app.schemas import QmsModuleConsumeResponse, QmsModuleOverviewItem, QmsModuleOverviewResponse, QmsModuleSessionResponse

router = APIRouter(prefix="/api/modules", tags=["qms_modules"])


def _badge_for(access: str) -> str:
    if access == "full":
        return "live"
    if access == "trial":
        return "trial"
    return "locked"


@router.get("/overview", response_model=QmsModuleOverviewResponse)
def modules_overview(
    user: CompanyUser = Depends(get_current_company_user),
    db: Session = Depends(get_db_session),
):
    today = utc_today()
    items: list[QmsModuleOverviewItem] = []
    for slug, module_name in SLUG_TO_MODULE.items():
        access, trial, _sub, msg = access_state(db, user.id, module_name, today=today, ensure_trial=False)
        badge = _badge_for(access)
        ar = actions_remaining_trial(trial) if trial else None
        dr = days_remaining_trial(trial, today) if trial else None
        notify = False
        if access == "trial" and trial:
            notify = dr is not None and (dr <= 2 or (ar is not None and ar <= 1))
        items.append(
            QmsModuleOverviewItem(
                slug=slug,
                module_name=module_name,
                access=access,
                badge=badge,
                actions_remaining=ar,
                days_remaining=dr,
                trial_expired_message=msg if access == "denied" and trial else None,
                notify_trial_ending=notify,
            )
        )
    return QmsModuleOverviewResponse(modules=items)


@router.post("/{slug}/session", response_model=QmsModuleSessionResponse)
def module_session(
    slug: str,
    user: CompanyUser = Depends(get_current_company_user),
    db: Session = Depends(get_db_session),
):
    module_name = resolve_module_slug(slug)
    if not module_name:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown module")
    today = utc_today()
    access, trial, _sub, msg = access_state(db, user.id, module_name, today=today, ensure_trial=True)
    if access == "denied":
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=msg or "Your trial has ended. Please enroll to continue using this module.",
        )
    slug_norm = next((s for s, m in SLUG_TO_MODULE.items() if m == module_name), slug.lower())
    return QmsModuleSessionResponse(
        module_name=module_name,
        slug=slug_norm,
        access=access,
        actions_remaining=None if access == "full" else (actions_remaining_trial(trial) if trial else None),
        days_remaining=None if access == "full" else (days_remaining_trial(trial, today) if trial else None),
    )


@router.post("/{slug}/consume-action", response_model=QmsModuleConsumeResponse)
def module_consume_action(
    slug: str,
    user: CompanyUser = Depends(get_current_company_user),
    db: Session = Depends(get_db_session),
):
    module_name = resolve_module_slug(slug)
    if not module_name:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown module")
    today = utc_today()
    access, trial, _sub, msg = access_state(db, user.id, module_name, today=today, ensure_trial=False)
    if access == "full":
        return QmsModuleConsumeResponse(ok=True, access="full", actions_remaining=None, days_remaining=None)
    if access != "trial" or trial is None:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=msg or "Your trial has ended. Please enroll to continue using this module.",
        )
    if trial.actions_used >= trial.usage_limit:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Your trial has ended. Please enroll to continue using this module.",
        )
    trial.actions_used += 1
    db.add(trial)
    db.commit()
    db.refresh(trial)
    return QmsModuleConsumeResponse(
        ok=True,
        access="trial",
        actions_remaining=actions_remaining_trial(trial),
        days_remaining=days_remaining_trial(trial, today),
    )
