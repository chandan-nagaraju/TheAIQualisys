"""Insert default module_pricing rows when the table is empty (dev / missed migration)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ModulePricing

_DEFAULT_ROWS: tuple[dict, ...] = (
    {
        "module_name": "fir_basic",
        "display_name": "Basic",
        "monthly_price": 2799,
        "yearly_price": None,
        "trial_days": 7,
        "usage_limit": 0,
        "fir_plan_type": "basic",
        "invoice_min": 0,
        "invoice_max": 1000,
        "highlight": None,
        "sort_order": 1,
    },
    {
        "module_name": "fir_pro",
        "display_name": "Pro",
        "monthly_price": 4599,
        "yearly_price": None,
        "trial_days": 7,
        "usage_limit": 0,
        "fir_plan_type": "pro",
        "invoice_min": 1001,
        "invoice_max": 2000,
        "highlight": None,
        "sort_order": 2,
    },
    {
        "module_name": "fir_enterprise",
        "display_name": "Enterprise",
        "monthly_price": 6599,
        "yearly_price": None,
        "trial_days": 7,
        "usage_limit": 0,
        "fir_plan_type": "enterprise",
        "invoice_min": 2001,
        "invoice_max": None,
        "highlight": "Best for growing companies",
        "sort_order": 3,
    },
    {
        "module_name": "drawings_directory",
        "display_name": "Drawings Directory",
        "monthly_price": 1999,
        "yearly_price": None,
        "trial_days": 14,
        "usage_limit": 5,
        "fir_plan_type": None,
        "invoice_min": None,
        "invoice_max": None,
        "highlight": None,
        "sort_order": 10,
    },
    {
        "module_name": "rc2a",
        "display_name": "RC2A",
        "monthly_price": 2499,
        "yearly_price": None,
        "trial_days": 14,
        "usage_limit": 5,
        "fir_plan_type": None,
        "invoice_min": None,
        "invoice_max": None,
        "highlight": None,
        "sort_order": 11,
    },
    {
        "module_name": "ppap",
        "display_name": "PPAP",
        "monthly_price": 3499,
        "yearly_price": None,
        "trial_days": 14,
        "usage_limit": 5,
        "fir_plan_type": None,
        "invoice_min": None,
        "invoice_max": None,
        "highlight": None,
        "sort_order": 12,
    },
    {
        "module_name": "iatf_documentation",
        "display_name": "IATF Documentation",
        "monthly_price": 4999,
        "yearly_price": None,
        "trial_days": 14,
        "usage_limit": 5,
        "fir_plan_type": None,
        "invoice_min": None,
        "invoice_max": None,
        "highlight": None,
        "sort_order": 13,
    },
)


def ensure_module_pricing_seeded(db: Session) -> None:
    n = db.execute(select(func.count()).select_from(ModulePricing)).scalar_one()
    if int(n) > 0:
        return
    for kwargs in _DEFAULT_ROWS:
        db.add(ModulePricing(**kwargs))
    db.commit()
