"""FIR Intelligence ingestion: deterministic event_uid, deduplicated inserts, batch summaries."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import FirReportEvent, FirUploadLog


@dataclass
class ParsedInvoiceRow:
    part_no: str
    invoice_no: str
    invoice_date: date
    quantity_str: str
    event_uid: str


@dataclass
class FirIngestSummary:
    rows_total: int
    rows_invalid: int
    new_records: int
    duplicate_records: int
    reports_generated: int


@dataclass
class FirBatchPreview:
    rows_total: int
    rows_invalid: int
    prospective_new: int
    prospective_duplicates: int


def _cell_str(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, float) and pd.isna(val):
        return ""
    return str(val).strip()


def _parse_invoice_date(val: Any) -> date | None:
    if val is None:
        return None
    if isinstance(val, float) and pd.isna(val):
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    s = str(val).strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        pass
    # Excel EU-style: 09.05.2026 — treat as invoice date (same semantic as canonical "Date" column).
    m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", s)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return date(year, month, day)
        except ValueError:
            return None
    ts = pd.to_datetime(s, errors="coerce", dayfirst=True)
    if pd.isna(ts):
        ts = pd.to_datetime(s, errors="coerce", dayfirst=False)
    if pd.isna(ts):
        return None
    return ts.date()


def _normalize_quantity(val: Any) -> str | None:
    if val is None:
        return None
    if isinstance(val, float) and pd.isna(val):
        return None
    s = str(val).strip().replace(",", "")
    if not s:
        return None
    # Allow integers and decimals; strip space/thin space
    s = s.replace("\u2009", "").replace("\u00a0", "")
    try:
        d = Decimal(s)
    except InvalidOperation:
        # "12 EA" -> try leading number
        m = re.match(r"^([-+]?\d+(?:\.\d+)?)", s)
        if not m:
            return None
        d = Decimal(m.group(1))
    if d != d.normalize():
        d = d.normalize()
    if d == d.to_integral():
        return str(int(d))
    t = format(d, "f")
    if "." in t:
        t = t.rstrip("0").rstrip(".")
    return t


def build_event_uid_key(
    *,
    company_id: int,
    invoice_number: str,
    invoice_date: date,
    part_number: str,
    quantity_normalized: str,
) -> str:
    inv = invoice_number.strip()
    pn = part_number.strip().upper()
    d = invoice_date.isoformat()
    q = quantity_normalized.strip()
    return f"{company_id}|{inv}|{d}|{pn}|{q}"


def hash_event_uid(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def parse_row_for_intelligence(row: dict[str, Any], *, company_id: int) -> ParsedInvoiceRow | None:
    pn_raw = row.get("Part Number") if "Part Number" in row else row.get("part_number")
    part_no = _cell_str(pn_raw).upper()
    if not part_no:
        return None

    inv_raw = row.get("Invoice Number") if "Invoice Number" in row else row.get("invoice_number")
    invoice_no = _cell_str(inv_raw)
    if not invoice_no:
        return None

    # Excel / fir_excel canonical column is "Date" — that IS the invoice date for intelligence + FIR.
    # Prefer it over separate "Invoice Date" / invoice_date keys when multiple exist.
    date_raw = None
    for label in ("Date", "date", "Invoice Date", "invoice_date"):
        if label in row:
            date_raw = row.get(label)
            break
    invoice_date = _parse_invoice_date(date_raw)
    if invoice_date is None:
        return None

    qty_raw = row.get("Quantity") if "Quantity" in row else row.get("quantity")
    quantity_str = _normalize_quantity(qty_raw)
    if quantity_str is None:
        return None

    key = build_event_uid_key(
        company_id=company_id,
        invoice_number=invoice_no,
        invoice_date=invoice_date,
        part_number=part_no,
        quantity_normalized=quantity_str,
    )
    uid = hash_event_uid(key)
    return ParsedInvoiceRow(
        part_no=part_no,
        invoice_no=invoice_no,
        invoice_date=invoice_date,
        quantity_str=quantity_str,
        event_uid=uid,
    )


def preview_fir_intelligence_batch(
    db: Session,
    *,
    company_id: int,
    parsed: list[ParsedInvoiceRow | None],
) -> FirBatchPreview:
    """Match ingest order: first occurrence of a uid in the batch may insert; later copies are duplicates."""
    rows_total = len(parsed)
    rows_invalid = sum(1 for p in parsed if p is None)
    valid_uids = [p.event_uid for p in parsed if p is not None]
    if not valid_uids:
        return FirBatchPreview(
            rows_total=rows_total,
            rows_invalid=rows_invalid,
            prospective_new=0,
            prospective_duplicates=0,
        )

    unique_needed = list(dict.fromkeys(valid_uids))  # preserve order, unique
    existing_db = {
        row[0]
        for row in db.execute(
            select(FirReportEvent.event_uid).where(
                FirReportEvent.company_id == company_id,
                FirReportEvent.event_uid.in_(unique_needed),
            )
        ).all()
    }

    seen_in_batch: set[str] = set()
    prospective_new = 0
    prospective_duplicates = 0
    simulated_committed = set(existing_db)

    for p in parsed:
        if p is None:
            continue
        u = p.event_uid
        if u in seen_in_batch:
            prospective_duplicates += 1
            continue
        seen_in_batch.add(u)
        if u in simulated_committed:
            prospective_duplicates += 1
        else:
            prospective_new += 1
            simulated_committed.add(u)

    return FirBatchPreview(
        rows_total=rows_total,
        rows_invalid=rows_invalid,
        prospective_new=prospective_new,
        prospective_duplicates=prospective_duplicates,
    )


def ingest_fir_intelligence_rows(
    db: Session,
    *,
    company_id: int,
    customer_id: int | None,
    rows: list[dict[str, Any]],
    source_file: str | None,
) -> FirIngestSummary:
    rows_total = len(rows)
    parsed_list: list[ParsedInvoiceRow | None] = [parse_row_for_intelligence(r, company_id=company_id) for r in rows]
    rows_invalid = sum(1 for p in parsed_list if p is None)

    uploaded_at = datetime.now(timezone.utc)

    new_records = 0
    duplicate_records = 0

    for p in parsed_list:
        if p is None:
            continue
        ev = FirReportEvent(
            company_id=company_id,
            customer_id=customer_id,
            part_no=p.part_no,
            invoice_no=p.invoice_no,
            event_uid=p.event_uid,
            invoice_date=p.invoice_date,
            quantity=p.quantity_str,
            source_file=source_file,
            uploaded_at=uploaded_at,
        )
        try:
            with db.begin_nested():
                db.add(ev)
                db.flush()
            new_records += 1
        except IntegrityError:
            duplicate_records += 1

    db.add(
        FirUploadLog(
            company_id=company_id,
            file_name=((source_file or "").strip()[:512] or None),
            rows_processed=rows_total,
            new_rows=new_records,
            duplicate_rows=duplicate_records,
            reports_generated=rows_total,
            uploaded_at=uploaded_at,
        )
    )

    return FirIngestSummary(
        rows_total=rows_total,
        rows_invalid=rows_invalid,
        new_records=new_records,
        duplicate_records=duplicate_records,
        reports_generated=rows_total,
    )
