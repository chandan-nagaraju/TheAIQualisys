"""Aggregates FIR report events for admin: cadence (running / regular / stranger) and per-customer stats."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import date, datetime, timezone
from statistics import median
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Customer, FirReportEvent, PartV2


def _utc_date(dt: datetime) -> date:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).date()


def _classify_rhythm(
    *,
    report_count: int,
    sorted_dates: list[date],
    today: date,
) -> str:
    """running ≤3d median gap; regular 3–10d; occasional 11–30d; stranger sparse or dormant >30d; new single recent."""
    if report_count == 0:
        return "new"
    last = sorted_dates[-1]
    days_since_last = (today - last).days

    if report_count == 1:
        return "new" if days_since_last <= 30 else "stranger"

    uniq_days = sorted(set(sorted_dates))
    if len(uniq_days) == 1:
        return "running"

    gaps: list[int] = []
    for a, b in zip(uniq_days, uniq_days[1:], strict=False):
        gaps.append((b - a).days)
    med = float(median(gaps))

    if days_since_last > 30:
        return "stranger"
    if med > 30:
        return "stranger"
    if med <= 3:
        return "running"
    if med <= 10:
        return "regular"
    return "occasional"


def build_fir_intelligence(db: Session, company_id: int, today: date | None = None) -> dict[str, Any]:
    today = today or datetime.now(timezone.utc).date()

    events = (
        db.execute(
            select(FirReportEvent)
            .where(FirReportEvent.company_id == company_id)
            .order_by(FirReportEvent.created_at)
        )
        .scalars()
        .all()
    )

    customers = (
        db.execute(select(Customer).where(Customer.company_id == company_id).order_by(Customer.name))
        .scalars()
        .all()
    )
    cust_by_id = {c.id: c for c in customers}

    parts = db.execute(select(PartV2).where(PartV2.company_id == company_id)).scalars().all()
    desc_by_part_no = {p.part_no.strip(): (p.description or "") for p in parts}

    # (customer_key, part_no) -> list of dates (one per event, preserves frequency on same day)
    by_key: dict[tuple[int | None, str], list[date]] = defaultdict(list)
    for ev in events:
        pn = (ev.part_no or "").strip()
        if not pn:
            continue
        cid = ev.customer_id
        if ev.invoice_date is not None:
            evday = ev.invoice_date
        else:
            evday = _utc_date(ev.created_at)
        by_key[(cid, pn)].append(evday)

    rhythm_counts: dict[str, int] = defaultdict(int)
    repeated_groups = 0
    part_rows: list[dict[str, Any]] = []

    for (cid, pn), dates in by_key.items():
        sorted_dates = sorted(dates)
        rc = len(sorted_dates)
        if rc > 1:
            repeated_groups += 1
        first_d, last_d = sorted_dates[0], sorted_dates[-1]
        span_days = max(1, (last_d - first_d).days + 1)
        avg_per_day = round(rc / span_days, 4)

        uniq = sorted(set(sorted_dates))
        gaps: list[int] = []
        for a, b in zip(uniq, uniq[1:], strict=False):
            gaps.append((b - a).days)
        med_interval = float(median(gaps)) if gaps else None

        rhythm = _classify_rhythm(report_count=rc, sorted_dates=sorted_dates, today=today)
        rhythm_counts[rhythm] += 1

        part_rows.append(
            {
                "customer_id": cid,
                "part_no": pn,
                "description": (desc_by_part_no.get(pn) or "")[:500],
                "report_count": rc,
                "is_repeat": rc > 1,
                "first_report_date": first_d.isoformat(),
                "last_report_date": last_d.isoformat(),
                "median_interval_days": med_interval,
                "days_since_last_report": (today - last_d).days,
                "avg_reports_per_day_in_span": avg_per_day,
                "rhythm": rhythm,
            }
        )

    # Per-customer rollups (include customers with zero events)
    by_customer: dict[int | None, list[dict[str, Any]]] = defaultdict(list)
    for row in part_rows:
        by_customer[row["customer_id"]].append(row)

    def customer_block(c: Customer | None, cid_key: int | None) -> dict[str, Any]:
        rows = by_customer.get(cid_key, [])
        total = sum(r["report_count"] for r in rows)
        if rows:
            dates_all: list[date] = []
            for r in rows:
                d0 = date.fromisoformat(r["first_report_date"])
                d1 = date.fromisoformat(r["last_report_date"])
                dates_all.extend([d0, d1])
            lo, hi = min(dates_all), max(dates_all)
            span = max(1, (hi - lo).days + 1)
            avg_day = round(total / span, 4)
        else:
            avg_day = 0.0
        return {
            "id": c.id if c else None,
            "vendor_code": c.vendor_code if c else None,
            "name": c.name if c else "Unassigned",
            "avg_reports_per_day": avg_day,
            "total_reports": total,
            "distinct_parts": len(rows),
            "parts": sorted(rows, key=lambda x: (-x["report_count"], x["part_no"])),
        }

    out_customers: list[dict[str, Any]] = [customer_block(c, c.id) for c in customers]
    if None in by_customer:
        out_customers.append(customer_block(None, None))

    rhythm_summary = {k: rhythm_counts[k] for k in sorted(rhythm_counts.keys())}

    return {
        "as_of": today.isoformat(),
        "company_id": company_id,
        "summary": {
            "total_report_events": len(events),
            "distinct_part_customer_pairs": len(by_key),
            "repeated_part_pairs": repeated_groups,
            "rhythm_part_pairs": rhythm_summary,
        },
        "customers": sorted(out_customers, key=lambda x: (x["name"] or "").lower()),
        "all_part_pairs": sorted(part_rows, key=lambda x: (-x["report_count"], x["part_no"])),
    }
