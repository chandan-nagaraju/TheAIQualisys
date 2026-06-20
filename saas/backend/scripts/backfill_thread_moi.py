"""
Backfill TPG Method of Inspection on existing metric thread part master rows.

Run from saas/backend:
  python3 scripts/backfill_thread_moi.py

Uses DATABASE_URL from .env. Safe to re-run (idempotent). Only updates thread rows.
"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models import PartCoatingV2, PartComplaintV2, PartSpecV2  # noqa: E402
from app.thread_moi import normalize_thread_method_of_inspection  # noqa: E402


def _backfill_table(session, model) -> int:
    updated = 0
    rows = session.scalars(select(model)).all()
    for row in rows:
        normalized = normalize_thread_method_of_inspection(
            row.parameter,
            row.specification,
            row.special_char,
            row.method_of_inspection,
        )
        current = (row.method_of_inspection or "").strip() or None
        if normalized != current:
            row.method_of_inspection = normalized
            updated += 1
    return updated


def main() -> None:
    with SessionLocal() as session:
        spec_n = _backfill_table(session, PartSpecV2)
        ccp_n = _backfill_table(session, PartComplaintV2)
        coat_n = _backfill_table(session, PartCoatingV2)
        session.commit()
    total = spec_n + ccp_n + coat_n
    print(
        f"Updated thread MOI on {total} row(s): "
        f"spec={spec_n}, ccp={ccp_n}, coating={coat_n}"
    )


if __name__ == "__main__":
    main()
