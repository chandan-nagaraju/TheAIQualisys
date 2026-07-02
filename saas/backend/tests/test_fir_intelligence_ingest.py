"""Pure unit tests for FIR Intelligence key building (no database)."""

from datetime import date

from app.fir_intelligence_ingest import (
    _parse_invoice_date,
    build_event_uid_key,
    hash_event_uid,
    parse_row_for_intelligence,
)


def test_parse_invoice_date_dd_mm_yyyy() -> None:
    assert _parse_invoice_date("09.05.2026") == date(2026, 5, 9)


def test_parse_invoice_date_iso() -> None:
    assert _parse_invoice_date("2026-05-09") == date(2026, 5, 9)


def test_parse_invoice_date_rejects_garbage_years() -> None:
    assert _parse_invoice_date("6475") is None
    assert _parse_invoice_date("35") is None
    assert _parse_invoice_date("3") is None
    assert _parse_invoice_date("26-27") is None
    assert _parse_invoice_date("3492/26-27") is None


def test_parse_invoice_date_excel_serial() -> None:
    # 45292 ≈ 2024-01-15 in Excel
    d = _parse_invoice_date(45292.0)
    assert d is not None
    assert 2020 <= d.year <= 2030


def test_event_uid_stable() -> None:
    key = build_event_uid_key(
        company_id=42,
        invoice_number=" INV-1 ",
        invoice_date=date(2026, 1, 15),
        part_number="abc-12",
        quantity_normalized="5",
    )
    assert "|" in key
    h1 = hash_event_uid(key)
    h2 = hash_event_uid(key)
    assert h1 == h2
    assert len(h1) == 64


def test_parse_row_prefers_date_column() -> None:
    row = {
        "Part Number": "p1",
        "Invoice Number": "n1",
        "Date": "2026-03-01",
        "Invoice Date": "2020-01-01",
        "Quantity": 10,
    }
    p = parse_row_for_intelligence(row, company_id=7)
    assert p is not None
    assert p.invoice_date == date(2026, 3, 1)


def test_parse_row_invalid_returns_none() -> None:
    assert parse_row_for_intelligence({"Part Number": ""}, company_id=1) is None
