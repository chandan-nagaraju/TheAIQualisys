"""
Apply DDL for Part PDF / revision history / password reset tokens.

Run from saas/backend after pulling model changes:
  python scripts/apply_schema_extensions.py

Uses DATABASE_URL from .env (same as the API).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from sqlalchemy import text

# Allow `python scripts/apply_schema_extensions.py` from saas/backend
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.database import engine  # noqa: E402


def _apply_sql_file(conn, path: Path) -> int:
    raw = path.read_text(encoding="utf-8")
    lines = [ln for ln in raw.splitlines() if not re.match(r"^\s*--", ln)]
    body = "\n".join(lines)
    stmts = [s.strip() + ";" for s in body.split(";") if s.strip()]
    for stmt in stmts:
        conn.execute(text(stmt))
    return len(stmts)


def main() -> None:
    mig_dir = _BACKEND / "migrations"
    files = sorted(mig_dir.glob("*.sql"))
    if not files:
        print("No migrations in", mig_dir)
        sys.exit(1)
    total = 0
    with engine.begin() as conn:
        for mig in files:
            n = _apply_sql_file(conn, mig)
            total += n
            print(f"Applied {n} statement(s) from {mig.name}")
    print(f"Total: {total} statement(s)")


if __name__ == "__main__":
    main()
