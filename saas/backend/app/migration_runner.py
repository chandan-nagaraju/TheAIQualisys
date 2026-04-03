from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

_MIGRATION_STATEMENT_TIMEOUT_MS = 60_000


def _split_sql_statements(raw_sql: str) -> list[str]:
    lines = [line for line in raw_sql.splitlines() if not re.match(r"^\s*--", line)]
    body = "\n".join(lines)
    return [stmt.strip() for stmt in body.split(";") if stmt.strip()]


def apply_sql_migrations(engine: Engine, backend_root: Path) -> None:
    """
    Best-effort SQL migration runner for environments without Alembic.
    Uses idempotent SQL files under saas/backend/migrations and tracks what was applied.
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

        applied = set(
            conn.execute(text("SELECT filename FROM schema_migrations")).scalars().all()
        )

        for migration in files:
            name = migration.name
            if name in applied:
                continue
            statements = _split_sql_statements(migration.read_text(encoding="utf-8"))
            conn.execute(text(f"SET LOCAL statement_timeout = {_MIGRATION_STATEMENT_TIMEOUT_MS}"))
            for stmt in statements:
                conn.execute(text(stmt))
            conn.execute(
                text("INSERT INTO schema_migrations (filename) VALUES (:filename)"),
                {"filename": name},
            )
