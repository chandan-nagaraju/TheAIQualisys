"""DB-backed module pricing and FIR plan usage caps."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ModulePricing, PlanType

# Fallback if table empty / row missing (before migration).
_FALLBACK_CAPS: dict[str, int | None] = {
    PlanType.basic.value: 1000,
    PlanType.pro.value: 2000,
    PlanType.enterprise.value: None,
}


def invoice_cap_for_plan(db: Session, plan_type: str) -> int | None:
    row = db.execute(select(ModulePricing).where(ModulePricing.fir_plan_type == plan_type)).scalar_one_or_none()
    if row:
        return row.invoice_max
    return _FALLBACK_CAPS.get(plan_type, 1000)


def list_fir_plan_rows(db: Session) -> list[ModulePricing]:
    return list(
        db.execute(
            select(ModulePricing)
            .where(ModulePricing.fir_plan_type.isnot(None))
            .order_by(ModulePricing.sort_order, ModulePricing.id)
        )
        .scalars()
        .all()
    )


def list_all_pricing_rows(db: Session) -> list[ModulePricing]:
    return list(
        db.execute(select(ModulePricing).order_by(ModulePricing.sort_order, ModulePricing.id)).scalars().all()
    )


def get_pricing_by_module_name(db: Session, module_name: str) -> ModulePricing | None:
    return db.execute(select(ModulePricing).where(ModulePricing.module_name == module_name)).scalar_one_or_none()


def qms_trial_defaults(db: Session, module_name: str) -> tuple[int, int]:
    row = get_pricing_by_module_name(db, module_name)
    if row:
        return row.trial_days, row.usage_limit
    return 14, 5
