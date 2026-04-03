#!/usr/bin/env python3
"""
CLI: sync legacy SQLite (Flask FIR) -> PostgreSQL SaaS v2 tables.

Usage (from saas/backend directory):
  python scripts/sync_sqlite_to_pg.py --vendor-code YOUR_VENDOR --sqlite ../legacy/database/fir.db
  python scripts/sync_sqlite_to_pg.py --company-id 2 --sqlite F:/beta/fir-automation/legacy/database/fir.db

Environment (optional):
  DATABASE_URL, LEGACY_SQLITE_PATH — defaults shown in --help.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # saas/backend
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.legacy_sync import sync_sqlite_to_postgres


def main() -> int:
    default_sqlite = ROOT.parent.parent / "legacy" / "database" / "fir.db"
    parser = argparse.ArgumentParser(description="Sync SQLite FIR data into PostgreSQL SaaS company.")
    parser.add_argument(
        "--sqlite",
        type=Path,
        default=Path(
            __import__("os").environ.get("LEGACY_SQLITE_PATH", str(default_sqlite))
        ),
        help="Path to fir.db",
    )
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--company-id", type=int, dest="company_id", help="Target companies.id in PostgreSQL")
    g.add_argument("--vendor-code", type=str, dest="vendor_code", help="Target companies.vendor_code")
    parser.add_argument(
        "--sqlite-company-id",
        type=int,
        default=1,
        help="Only import SQLite rows with this company_id (legacy default 1). Ignored if column missing.",
    )
    parser.add_argument(
        "--with-invoices",
        action="store_true",
        help="Replace invoices_v2 for the target company from SQLite Invoices table.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate connections and target company only; no writes.",
    )
    args = parser.parse_args()

    get_settings()  # load .env from cwd
    if args.dry_run:
        with SessionLocal() as pg:
            from app.legacy_sync import resolve_target_company

            c = resolve_target_company(
                pg,
                company_id=args.company_id,
                vendor_code=args.vendor_code,
            )
            print(f"OK dry-run: would sync into company id={c.id} vendor_code={c.vendor_code!r}")
            print(f"SQLite: {args.sqlite.resolve()}")
        return 0

    if not args.sqlite.is_file():
        print(f"Error: SQLite file not found: {args.sqlite}", file=sys.stderr)
        return 1

    db: Session = SessionLocal()
    try:
        result = sync_sqlite_to_postgres(
            db,
            sqlite_path=args.sqlite,
            target_company_id=args.company_id,
            target_vendor_code=args.vendor_code,
            sqlite_company_id=args.sqlite_company_id,
            sync_invoices=args.with_invoices,
            replace_existing_parts=True,
        )
        db.commit()
        print(
            f"Done. SQLite parts seen: {result.sqlite_parts_seen}; "
            f"PG parts upserted: {result.parts_upserted}; "
            f"spec rows written: {result.specs_written}; "
            f"invoices written: {result.invoices_written}"
        )
    except Exception as e:
        db.rollback()
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
