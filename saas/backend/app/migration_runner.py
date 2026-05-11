from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

_MIGRATION_STATEMENT_TIMEOUT_MS = 60_000
# 009_fir_events_intelligence can run heavy backfill + dedupe; 60s often kills production deploys.
_HEAVY_MIGRATION_TIMEOUT_MS = 900_000  # 15 minutes


def _statement_timeout_ms_for_migration(filename: str) -> int:
    if filename.startswith("009_") or filename.startswith("010_"):
        return _HEAVY_MIGRATION_TIMEOUT_MS
    return _MIGRATION_STATEMENT_TIMEOUT_MS


def _strip_outer_transaction_directives(sql: str) -> str:
    """
    Remove one leading BEGIN; and one trailing COMMIT; so the script runs inside the
    migration runner's transaction. Needed for files that are written to run standalone
    in psql (e.g. FIR intelligence migration with PL/pgSQL blocks).
    """
    s = sql.strip()
    s = re.sub(r"^\s*BEGIN\s*;\s*", "", s, count=1, flags=re.IGNORECASE)
    s = re.sub(r"\s*COMMIT\s*;\s*$", "", s, count=1, flags=re.IGNORECASE)
    return s.strip()


def apply_sql_migrations(engine: Engine, backend_root: Path) -> None:
    """
    Best-effort SQL migration runner for environments without Alembic.
    Each file is executed as a single script (PostgreSQL multi-statement), which preserves
    dollar-quoted PL/pgSQL bodies. Splitting on ';' would break DO $$ ... $$ blocks.
    """
    migrations_dir = backend_root / "migrations"
    files = sorted(migrations_dir.glob("*.sql"))
    if not files:
        return

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    filename VARCHAR(255) PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )
        # Use DBAPI fetchall + driver-native INSERT to avoid SQLAlchemy bound-parameter
        # edge cases that raised immutabledict TypeError on some Railway/psycopg2 builds.
        applied = {row[0] for row in conn.exec_driver_sql("SELECT filename FROM schema_migrations").fetchall()}

    for migration in files:
        name = migration.name
        if name in applied:
            continue
        raw = migration.read_text(encoding="utf-8")
        body = _strip_outer_transaction_directives(raw)
        if not body:
            continue
        timeout_ms = _statement_timeout_ms_for_migration(name)
        with engine.begin() as conn:
            conn.exec_driver_sql(f"SET LOCAL statement_timeout = {timeout_ms}")
            conn.exec_driver_sql(body)
            conn.exec_driver_sql("INSERT INTO schema_migrations (filename) VALUES (%s)", (name,))
