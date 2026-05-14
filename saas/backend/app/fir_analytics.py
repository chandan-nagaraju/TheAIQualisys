"""Aggregates FIR report events for admin: cadence (running / regular / stranger) and per-customer stats."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from statistics import median
from typing import Any

def _utc_date(dt: datetime) -> date:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).date()


def _last_day_of_calendar_month(year: int, month: int) -> date:
    if month == 12:
        return date(year, 12, 31)
    return date(year, month + 1, 1) - timedelta(days=1)


def _fir_event_invoice_day(ev: FirReportEvent) -> date:
    if ev.invoice_date is not None:
        return ev.invoice_date
    return _utc_date(ev.created_at)


def _event_day_for_fy_series(ev: Any, *, use_invoice_date: bool) -> date:
    """FY chart bucketing: either invoice business date or logged-at date."""
    if use_invoice_date:
        inv = getattr(ev, "invoice_date", None)
        if inv is not None:
            return inv if isinstance(inv, date) else date.fromisoformat(str(inv))
    ca = getattr(ev, "created_at", None)
    if ca is None:
        raise ValueError("event missing created_at")
    return _utc_date(ca if isinstance(ca, datetime) else datetime.fromisoformat(str(ca)))


def _parse_quantity_numeric(qty: str | None) -> float | None:
    """Parse stored fir_events.quantity (normalized string) to float for median; mirrors ingest normalization loosely."""
    if qty is None:
        return None
    s = str(qty).strip().replace(",", "")
    if not s:
        return None
    s = s.replace("\u2009", "").replace("\u00a0", "")
    try:
        d = Decimal(s)
    except InvalidOperation:
        m = re.match(r"^([-+]?\d+(?:\.\d+)?)", s)
        if not m:
            return None
        try:
            d = Decimal(m.group(1))
        except InvalidOperation:
            return None
    return float(d)


def _median_quantity_from_event_qty_strings(qty_strings: list[str]) -> float | None:
    """Median order qty for admin \"Expected QTY\".

    Historical migrations and merge-010 stored placeholder ``0`` when quantity was unknown, so an
    all-zero series is treated as *no data* (None → UI em dash).

    When there is a mix of zeros and positive quantities (typical: legacy placeholders + newer
    ingests with real qty), median is taken over **positive** values only so placeholders do not
    drown out real orders. Genuine zero-qty lines are rare in this domain; if you need strict
    median including zeros, revisit this heuristic.
    """
    nums: list[float] = []
    for s in qty_strings:
        n = _parse_quantity_numeric(s)
        if n is not None:
            nums.append(n)
    if not nums:
        return None
    if all(n == 0.0 for n in nums):
        return None
    positive = [n for n in nums if n > 0]
    if positive:
        return float(median(positive))
    return float(median(nums))


def fy_april_start_year_for_date(d: date) -> int:
    """Indian financial year begins in April: return the calendar year of that April 1."""
    return d.year if d.month >= 4 else d.year - 1


def build_fy_monthly_report_series(
    events: Iterable[Any],
    fy_start_year: int,
    *,
    use_invoice_date: bool = False,
) -> list[dict[str, Any]]:
    """Count FIR rows by calendar month for Apr (Y) through Mar (Y+1)."""
    start = date(fy_start_year, 4, 1)
    end_excl = date(fy_start_year + 1, 4, 1)
    counts = [0] * 12
    for ev in events:
        d = _event_day_for_fy_series(ev, use_invoice_date=use_invoice_date)
        if d < start or d >= end_excl:
            continue
        idx = (d.month - 4) % 12
        counts[idx] += 1

    month_nums = [
        (4, fy_start_year),
        (5, fy_start_year),
        (6, fy_start_year),
        (7, fy_start_year),
        (8, fy_start_year),
        (9, fy_start_year),
        (10, fy_start_year),
        (11, fy_start_year),
        (12, fy_start_year),
        (1, fy_start_year + 1),
        (2, fy_start_year + 1),
        (3, fy_start_year + 1),
    ]
    month_abbr = ["Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar"]
    out: list[dict[str, Any]] = []
    for i, (m, y) in enumerate(month_nums):
        yy = y % 100
        out.append(
            {
                "year": y,
                "month": m,
                "label": f"{month_abbr[i]} '{yy:02d}",
                "count": counts[i],
            }
        )
    return out


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


def build_fir_intelligence(
    db: Session,
    company_id: int,
    *,
    filter_year: int,
    filter_month: int,
    qty_reliable_since: date | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    real_today = today or datetime.now(timezone.utc).date()
    month_start = date(filter_year, filter_month, 1)
    month_end = _last_day_of_calendar_month(filter_year, filter_month)
    as_of = min(real_today, month_end)

    events: list[FirReportEvent] = (
        db.execute(
            select(FirReportEvent)
            .where(FirReportEvent.company_id == company_id)
            .order_by(FirReportEvent.created_at)
        )
        .scalars()
        .all()
    )

    filtered = [e for e in events if month_start <= _fir_event_invoice_day(e) <= month_end]

    customers = (
        db.execute(select(Customer).where(Customer.company_id == company_id).order_by(Customer.name))
        .scalars()
        .all()
    )

    parts = db.execute(select(PartV2).where(PartV2.company_id == company_id)).scalars().all()
    desc_by_part_no = {p.part_no.strip(): (p.description or "") for p in parts}

    # (customer_key, part_no) -> list of (event_date, quantity_str) — rows in selected month only
    by_key: dict[tuple[int | None, str], list[tuple[date, str]]] = defaultdict(list)
    for ev in filtered:
        pn = (ev.part_no or "").strip()
        if not pn:
            continue
        cid = ev.customer_id
        evday = _fir_event_invoice_day(ev)
        qty_raw = (ev.quantity or "").strip()
        by_key[(cid, pn)].append((evday, qty_raw))

    rhythm_counts: dict[str, int] = defaultdict(int)
    repeated_groups = 0
    part_rows: list[dict[str, Any]] = []

    for (cid, pn), pairs in by_key.items():
        pairs_sorted = sorted(pairs, key=lambda x: (x[0], x[1]))
        sorted_dates = [d for d, _ in pairs_sorted]
        qty_for_median = [
            q for d, q in pairs_sorted if qty_reliable_since is None or d >= qty_reliable_since
        ]
        median_qty = _median_quantity_from_event_qty_strings(qty_for_median)
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

        rhythm = _classify_rhythm(report_count=rc, sorted_dates=sorted_dates, today=as_of)
        rhythm_counts[rhythm] += 1

        part_rows.append(
            {
                "customer_id": cid,
                "part_no": pn,
                "description": (desc_by_part_no.get(pn) or "")[:500],
                "report_count": rc,
                "median_quantity": median_qty,
                "is_repeat": rc > 1,
                "first_report_date": first_d.isoformat(),
                "last_report_date": last_d.isoformat(),
                "median_interval_days": med_interval,
                "days_since_last_report": (as_of - last_d).days,
                "avg_reports_per_day_in_span": avg_per_day,
                "rhythm": rhythm,
            }
        )

    # Per-customer rollups (include customers with zero events in this month)
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

    fy_start = fy_april_start_year_for_date(month_start)
    fy_series = build_fy_monthly_report_series(events, fy_start, use_invoice_date=True)
    fy_label = f"{fy_start}-{str(fy_start + 1)[-2:]}"

    return {
        "as_of": as_of.isoformat(),
        "company_id": company_id,
        "view": {
            "year": filter_year,
            "month": filter_month,
            "month_start": month_start.isoformat(),
            "month_end": month_end.isoformat(),
            "qty_reliable_since": qty_reliable_since.isoformat() if qty_reliable_since else None,
        },
        "fy_monthly_reports": {
            "fy_start_year": fy_start,
            "fy_label": fy_label,
            "months": fy_series,
            "fy_total": sum(m["count"] for m in fy_series),
        },
        "summary": {
            "total_report_events": len(filtered),
            "distinct_part_customer_pairs": len(by_key),
            "repeated_part_pairs": repeated_groups,
            "rhythm_part_pairs": rhythm_summary,
        },
        "customers": sorted(out_customers, key=lambda x: (x["name"] or "").lower()),
        "all_part_pairs": sorted(part_rows, key=lambda x: (-x["report_count"], x["part_no"])),
    }
