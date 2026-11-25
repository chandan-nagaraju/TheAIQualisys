from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from sqlalchemy.sql.dml import Delete

from app.part_complaints import CCP_RETENTION_DAYS, complaint_retention_cutoff, purge_expired_part_complaints


def test_complaint_retention_is_ninety_days():
    now = datetime(2026, 11, 25, 10, 0, tzinfo=timezone.utc)
    assert CCP_RETENTION_DAYS == 90
    assert complaint_retention_cutoff(now) == now - timedelta(days=90)


def test_purge_expired_part_complaints_deletes_stale_rows():
    db = MagicMock()
    db.execute.return_value = SimpleNamespace(rowcount=2)
    now = datetime(2026, 11, 25, tzinfo=timezone.utc)
    n = purge_expired_part_complaints(db, 44, now=now)
    assert n == 2
    op = db.execute.call_args[0][0]
    assert isinstance(op, Delete)
    assert op.table.name == "part_complaints_v2"
    db.flush.assert_called()
    db.commit.assert_not_called()
