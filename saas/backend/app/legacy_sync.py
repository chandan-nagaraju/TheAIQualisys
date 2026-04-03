"""
Copy master data from the legacy SQLite FIR database into PostgreSQL (SaaS v2 tables).

Maps:
  parts_master + part_spec_data -> parts_v2 + part_specs_v2
  Invoices (optional)         -> invoices_v2

Always scopes writes to a single target company row in PostgreSQL (multi-tenant safe).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Company, InvoiceV2, PartSpecV2, PartV2


def _sqlite_table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return {str(row[1]) for row in cur.fetchall()}


def _pick_sqlite_company_filter(columns: set[str], sqlite_company_id: int) -> tuple[str, list]:
    if "company_id" not in columns:
        return "1 = ?", [1]
    # Pre-migration rows often have NULL company_id; treat as legacy tenant 1 only.
    if sqlite_company_id == 1:
        return "(company_id IS NULL OR company_id = ?)", [sqlite_company_id]
    return "company_id = ?", [sqlite_company_id]


def _parse_upload_date(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(timezone.utc)
    raw = str(raw).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            dt = datetime.strptime(raw[:19], fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return datetime.now(timezone.utc)


@dataclass
class SyncResult:
    parts_upserted: int
    specs_written: int
    invoices_written: int
    sqlite_parts_seen: int


def resolve_target_company(db: Session, *, company_id: int | None, vendor_code: str | None) -> Company:
    if company_id is not None:
        c = db.get(Company, company_id)
        if not c:
            raise ValueError(f"No PostgreSQL company with id={company_id}")
        return c
    if vendor_code:
        vc = vendor_code.strip()
        c = db.execute(select(Company).where(Company.vendor_code == vc)).scalar_one_or_none()
        if not c:
            raise ValueError(f"No PostgreSQL company with vendor_code={vc!r}")
        return c
    raise ValueError("Provide target_company_id or target_vendor_code")


def sync_sqlite_to_postgres(
    pg: Session,
    *,
    sqlite_path: str | Path,
    target_company_id: int | None = None,
    target_vendor_code: str | None = None,
    sqlite_company_id: int = 1,
    sync_invoices: bool = False,
    replace_existing_parts: bool = True,
) -> SyncResult:
    """
    :param replace_existing_parts: If True, for each synced part, existing part_specs_v2 rows
        for that part are removed and replaced from SQLite. Part rows are updated in place by part_no.
    """
    path = Path(sqlite_path)
    if not path.is_file():
        raise FileNotFoundError(f"SQLite database not found: {path}")

    company = resolve_target_company(
        pg, company_id=target_company_id, vendor_code=target_vendor_code
    )
    target_cid = company.id

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row

    pm_cols = _sqlite_table_columns(conn, "parts_master")
    if not pm_cols:
        raise RuntimeError("SQLite has no parts_master table")

    ps_cols = _sqlite_table_columns(conn, "part_spec_data")
    wh_parts, args_parts = _pick_sqlite_company_filter(pm_cols, sqlite_company_id)
    sql_parts = f"SELECT * FROM parts_master WHERE {wh_parts} ORDER BY part_no"
    part_rows = conn.execute(sql_parts, args_parts).fetchall()
    seen = len(part_rows)

    parts_upserted = 0
    specs_written = 0

    for row in part_rows:
        part_no = str(row["part_no"]).strip()
        if not part_no:
            continue
        sqlite_pid = int(row["part_id"])
        drawing_rev = row["drawing_rev"] if row["drawing_rev"] is not None else None
        description = row["description"] if row["description"] is not None else None

        existing = pg.execute(
            select(PartV2).where(
                PartV2.company_id == target_cid,
                PartV2.part_no == part_no,
            )
        ).scalar_one_or_none()

        if existing:
            existing.drawing_rev = drawing_rev
            existing.description = description
            pg_part = existing
        else:
            pg_part = PartV2(
                company_id=target_cid,
                part_no=part_no,
                drawing_rev=drawing_rev,
                description=description,
            )
            pg.add(pg_part)
            pg.flush()

        parts_upserted += 1

        if replace_existing_parts and ps_cols:
            wh_spec = "part_id = ?"
            spec_args: list = [sqlite_pid]
            if "company_id" in ps_cols:
                if sqlite_company_id == 1:
                    wh_spec += " AND (company_id IS NULL OR company_id = ?)"
                else:
                    wh_spec += " AND company_id = ?"
                spec_args.append(sqlite_company_id)
            spec_rows = conn.execute(
                f"SELECT * FROM part_spec_data WHERE {wh_spec} ORDER BY id",
                spec_args,
            ).fetchall()

            pg.execute(delete(PartSpecV2).where(PartSpecV2.part_id == pg_part.id))
            for sr in spec_rows:
                param = (sr["parameter"] or "").strip() or "—"
                pg.add(
                    PartSpecV2(
                        part_id=pg_part.id,
                        parameter=param,
                        specification=sr["specification"],
                        special_char=sr["special_char"],
                        method_of_inspection=sr["method_of_inspection"],
                    )
                )
                specs_written += 1

    invoices_written = 0
    if sync_invoices:
        inv_cols = _sqlite_table_columns(conn, "Invoices")
        if inv_cols:
            wh_inv, args_inv = _pick_sqlite_company_filter(inv_cols, sqlite_company_id)
            inv_rows = conn.execute(
                f"SELECT * FROM Invoices WHERE {wh_inv} ORDER BY id",
                args_inv,
            ).fetchall()
            pg.execute(delete(InvoiceV2).where(InvoiceV2.company_id == target_cid))
            for ir in inv_rows:
                num = ir["invoice_number"]
                up = ir["upload_date"] if "upload_date" in ir.keys() else None
                created = _parse_upload_date(up)
                pg.add(
                    InvoiceV2(
                        company_id=target_cid,
                        invoice_number=str(num) if num is not None else None,
                        created_at=created,
                    )
                )
                invoices_written += 1

    conn.close()

    return SyncResult(
        parts_upserted=parts_upserted,
        specs_written=specs_written,
        invoices_written=invoices_written,
        sqlite_parts_seen=seen,
    )
