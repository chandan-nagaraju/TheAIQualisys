"""Ensure default module_pricing rows exist (dev / missed migration)."""

from __future__ import annotations

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
        "listing_active": False,
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
        "listing_active": False,
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
        "listing_active": False,
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
        "listing_active": False,
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
        "listing_active": False,
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
        "listing_active": False,
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
        "listing_active": False,
        "sort_order": 13,
    },
)




def backfill_listing_active_column(db: Session) -> None:
    """Existing DBs: ensure listing_active exists and QMS rows default to off."""
    from sqlalchemy import text as sql_text
    try:
        db.execute(sql_text(
            "ALTER TABLE module_pricing ADD COLUMN IF NOT EXISTS listing_active BOOLEAN NOT NULL DEFAULT false"
        ))
        db.commit()
    except Exception:
        db.rollback()
    try:
        db.execute(sql_text(
            "UPDATE module_pricing SET listing_active = false WHERE fir_plan_type IS NULL AND listing_active IS NULL"
        ))
        db.commit()
    except Exception:
        db.rollback()

def ensure_module_pricing_seeded(db: Session) -> None:
    backfill_listing_active_column(db)
    # Backfill missing defaults even if some rows already exist.
    # Older deployments can have partial data after incremental releases.
    # Raw SQL + fetchall avoids ScalarResult/set edge cases on some SQLAlchemy/psycopg2 builds.
    from sqlalchemy import text as sql_text

    existing: set[str] = set()
    for row in db.execute(sql_text("SELECT module_name FROM module_pricing")).fetchall():
        existing.add(str(row[0]))
    missing = [kwargs for kwargs in _DEFAULT_ROWS if kwargs["module_name"] not in existing]
    if not missing:
        return
    for kwargs in missing:
        db.add(ModulePricing(**kwargs))
    db.commit()
