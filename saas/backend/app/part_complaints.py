"""Customer complaint (CPI) rows expire 90 days after last update."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import PartComplaintV2

CCP_RETENTION_DAYS = 90


def complaint_retention_cutoff(now: datetime | None = None) -> datetime:
    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp - timedelta(days=CCP_RETENTION_DAYS)


def purge_expired_part_complaints(db: Session, part_id: int, *, now: datetime | None = None) -> int:
    """Delete complaint rows last updated more than 90 days ago. FIR then shows No CPI."""
    cutoff = complaint_retention_cutoff(now)
    result = db.execute(
        delete(PartComplaintV2).where(
            PartComplaintV2.part_id == part_id,
            PartComplaintV2.updated_at < cutoff,
        )
    )
    deleted = int(result.rowcount or 0)
    if deleted:
        db.flush()
    return deleted
