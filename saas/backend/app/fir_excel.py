"""Excel invoice parsing — same column mapping as legacy Flask app.py upload route."""

from __future__ import annotations

import io
import re
from typing import Any

import pandas as pd

from app.part_field_validation import sanitize_part_master_alnum_upper

def _norm_header(s: Any) -> str:
    text = str(s or "").strip().lower()
    # Normalize punctuation and separators so variants like
    # "Invoice/DC No.", "Invoice DC No", "invoice-dc no" all match.
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


COLUMN_MAPPING = {
    "part number": "Part Number",
    "part no": "Part Number",
    "part no ": "Part Number",
    "part_no": "Part Number",
    "part": "Part Number",
    "material code": "Part Number",
    "materialcode": "Part Number",
    "description": "Description",
    "material desc": "Description",
    "material description": "Description",
    "qty": "Quantity",
    "quantity": "Quantity",
    "advised qty": "Quantity",
    "advised quantity": "Quantity",
    "invoice no": "Invoice Number",
    "invoice number": "Invoice Number",
    "invoice": "Invoice Number",
    "invoice dc no": "Invoice Number",
    "invoice dc number": "Invoice Number",
    "dc no": "Invoice Number",
    "dc number": "Invoice Number",
    "date": "Date",
    "dc date": "Date",
    "document date": "Date",
}

DISPLAY_COLS = [
    "Part Number",
    "Description",
    "Quantity",
    "Invoice Number",
    "Date",
]

# Excel 97–2003 .xls (OLE compound document)
_OLE2_MAGIC = bytes.fromhex("d0cf11e0a1b11ae1")


def _invoice_excel_engine(content: bytes, filename: str | None) -> str:
    """
    Pick pandas engine without relying on filename alone (some clients omit or alter it).
    .xlsx is ZIP (PK); legacy .xls is OLE2.
    """
    if len(content) >= 2 and content[:2] == b"PK":
        return "openpyxl"
    if len(content) >= len(_OLE2_MAGIC) and content[: len(_OLE2_MAGIC)] == _OLE2_MAGIC:
        return "xlrd"
    fn = (filename or "").lower()
    if fn.endswith(".xls") and not fn.endswith(".xlsx"):
        return "xlrd"
    return "openpyxl"


def parse_invoice_excel(content: bytes, *, filename: str | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    """Read .xlsx via openpyxl; Excel 97–2003 .xls via xlrd (BIFF)."""
    primary = _invoice_excel_engine(content, filename)
    secondary = "openpyxl" if primary == "xlrd" else "xlrd"
    buf = io.BytesIO(content)
    try:
        df = pd.read_excel(buf, engine=primary)
    except Exception:
        buf = io.BytesIO(content)
        df = pd.read_excel(buf, engine=secondary)
    # Build target columns explicitly so multiple source columns can map to the
    # same canonical field without creating duplicate labels.
    matched_sources: dict[str, list[Any]] = {k: [] for k in DISPLAY_COLS}
    for col in df.columns:
        key = _norm_header(col)
        canon = COLUMN_MAPPING.get(key)
        if canon:
            matched_sources[canon].append(col)

    extracted = pd.DataFrame(index=df.index)
    for canon in DISPLAY_COLS:
        src_cols = matched_sources.get(canon, [])
        if not src_cols:
            extracted[canon] = ""
            continue
        if len(src_cols) == 1:
            extracted[canon] = df[src_cols[0]].fillna("")
            continue
        # If multiple source columns map to the same canonical column (e.g. Date + DC Date),
        # keep the first non-empty value per row.
        sub = df[src_cols].fillna("")
        extracted[canon] = sub.apply(
            lambda row: next((str(v).strip() for v in row if str(v).strip()), ""),
            axis=1,
        )

    for col in DISPLAY_COLS:
        extracted[col] = extracted[col].map(lambda v: "" if v is None else str(v).strip())
    # Keep only rows that contain at least one of the required output values.
    extracted = extracted[
        extracted.apply(lambda r: any(str(v).strip() for v in r.values), axis=1)
    ]
    # Business rule: Part Number can repeat, Invoice Number must be unique.
    # Ignore blank invoice numbers here; required-field validation happens in UI/workflow.
    invoice_series = extracted["Invoice Number"].map(lambda v: str(v).strip())
    seen: set[str] = set()
    dupes: list[str] = []
    for inv in invoice_series:
        if not inv:
            continue
        if inv in seen and inv not in dupes:
            dupes.append(inv)
        seen.add(inv)
    if dupes:
        dupes_str = ", ".join(dupes[:5])
        extra = f" (+{len(dupes) - 5} more)" if len(dupes) > 5 else ""
        raise ValueError(
            "Invoice Number must be unique. Duplicate invoice number(s): "
            f"{dupes_str}{extra}"
        )
    rows = extracted.to_dict(orient="records")
    for row in rows:
        pn = row.get("Part Number")
        if pn is not None:
            row["Part Number"] = sanitize_part_master_alnum_upper(str(pn))
    return rows, DISPLAY_COLS


def sample_size_for_quantity(qty_val: float) -> int | str:
    if qty_val <= 0:
        return ""
    if qty_val <= 5:
        return 2
    if qty_val <= 10:
        return 3
    return 5


def enrich_rows_with_parts(
    rows: list[dict],
    *,
    parts_by_no: dict[str, tuple[str | None, int | None]] | None = None,
    part_rows: list[tuple[str, str | None, int, int]] | None = None,
    workspace_customer_id: int | None = None,
    param_count_by_part_id: dict[int, int] | None = None,
    default_num_params: int = 17,
) -> list[dict]:
    """Resolve part master row per invoice line using customer-scoped parts when ``part_rows`` is set."""
    from collections import defaultdict

    param_count_by_part_id = param_count_by_part_id or {}
    by_pn: dict[str, list[tuple[str | None, int, int]]] = defaultdict(list)
    if part_rows is not None:
        for pno, dr, pid, cid in part_rows:
            by_pn[str(pno).strip()].append((dr, pid, cid))
    elif parts_by_no is not None:
        for pno, (dr, pid) in parts_by_no.items():
            by_pn[str(pno).strip()].append((dr, pid if pid is not None else -1, -1))
    out = []
    for r in rows:
        row = dict(r)
        part_no = str(row.get("Part Number", "")).strip()
        draw_rev: str | None = None
        part_id: int | None = None
        cands = by_pn.get(part_no, [])
        if not cands:
            pass
        elif len(cands) == 1:
            dr, pid, _cid = cands[0]
            draw_rev = dr
            part_id = None if pid == -1 else pid
        elif workspace_customer_id is not None:
            for dr, pid, cid in cands:
                if cid == workspace_customer_id:
                    draw_rev, part_id = dr, pid
                    break
        try:
            qty_val = float(row.get("Quantity") or 0)
        except (TypeError, ValueError):
            qty_val = 0
        row["draw_rev"] = draw_rev or ""
        row["sample_size"] = sample_size_for_quantity(qty_val)
        if part_id is not None and part_id > 0:
            row["num_params"] = param_count_by_part_id.get(part_id, default_num_params)
        else:
            row["num_params"] = default_num_params
        out.append(row)
    return out
