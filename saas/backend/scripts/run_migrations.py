"""Apply pending SQL migrations before the API process starts (Railway / Render).

Uses DATABASE_URL (same as the FastAPI app). Exits with code 1 on failure so the
deploy does not start the server.
"""

from __future__ import annotations

import logging
import sys

from sqlalchemy import create_engine

from app.config import get_settings
from app.migration_runner import apply_sql_migrations


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logger = logging.getLogger(__name__)
    settings = get_settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    try:
        apply_sql_migrations(engine, settings.backend_root)
    except Exception as e:
        logger.exception("Migration failed: %s", e)
        return 1
    logger.info("All pending migrations are up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
