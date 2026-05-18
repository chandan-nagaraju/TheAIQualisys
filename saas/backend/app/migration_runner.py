from __future__ import annotations

import logging
import re
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

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


def _execute_migration_sql_batch(conn, sql: str, *, timeout_ms: int) -> None:
    """
    Run a full `.sql` file as one server batch.

    We use the DB-API cursor directly (no SQLAlchemy ``exec_driver_sql`` on the full
    script).  PL/pgSQL uses ``%`` in ``RAISE NOTICE '... %', var;`` — SQLAlchemy
    interprets ``%`` as pyformat placeholders for psycopg2 and ends up calling
    ``cursor.execute(stmt, immutabledict(...))``, which raises
    ``TypeError: immutabledict is not a sequence``.
    """
    dbapi = conn.connection.dbapi_connection
    cur = dbapi.cursor()
    try:
        cur.execute(f"SET LOCAL statement_timeout = {int(timeout_ms)}")
        cur.execute(sql)
    finally:
        cur.close()


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
                CREATE TABLE IF NOT EXISTS public.schema_migrations (
                    filename TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )
        # Use DBAPI fetchall + driver-native INSERT to avoid SQLAlchemy bound-parameter
        # edge cases that raised immutabledict TypeError on some Railway/psycopg2 builds.
        applied = {
            row[0]
            for row in conn.exec_driver_sql("SELECT filename FROM public.schema_migrations").fetchall()
        }

    for migration in files:
        name = migration.name
        if name in applied:
            continue
        raw = migration.read_text(encoding="utf-8")
        body = _strip_outer_transaction_directives(raw)
        if not body:
            continue
        timeout_ms = _statement_timeout_ms_for_migration(name)
        logger.info("Applying migration %s", name)
        with engine.begin() as conn:
            _execute_migration_sql_batch(conn, body, timeout_ms=timeout_ms)
            conn.exec_driver_sql(
                "INSERT INTO public.schema_migrations (filename) VALUES (%s)",
                (name,),
            )
        logger.info("Migration applied successfully: %s", name)
