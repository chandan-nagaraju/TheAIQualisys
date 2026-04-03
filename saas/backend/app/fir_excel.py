"""Excel invoice parsing — same column mapping as legacy Flask app.py upload route."""

from __future__ import annotations

import io
from typing import Any

import pandas as pd

COLUMN_MAPPING = {
    "part number": "Part Number",
    "part_no": "Part Number",
    "part": "Part Number",
    "material code": "Part Number",
    "description": "Description",
    "material desc.": "Description",
    "material desc": "Description",
    "qty": "Quantity",
    "quantity": "Quantity",
    "advised qty": "Quantity",
    "invoice no": "Invoice Number",
    "invoice": "Invoice Number",
    "invoice/dc no.": "Invoice Number",
    "invoice/dc no": "Invoice Number",
    "date": "Date",
    "dc date": "Date",
}

DISPLAY_COLS = [
    "Part Number",
    "Description",
    "Quantity",
    "Invoice Number",
    "Date",
]


def parse_invoice_excel(content: bytes) -> tuple[list[dict[str, Any]], list[str]]:
    df = pd.read_excel(io.BytesIO(content))
    normalized_cols = {}
    for col in df.columns:
        key = str(col).strip().lower()
        if key in COLUMN_MAPPING:
            normalized_cols[col] = COLUMN_MAPPING[key]
    df_renamed = df.rename(columns=normalized_cols)
    extracted = df_renamed.reindex(columns=DISPLAY_COLS)
    extracted = extracted.fillna("")
    rows = extracted.to_dict(orient="records")
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
    parts_by_no: dict[str, tuple[str | None, int | None]],
    param_count_by_part_id: dict[int, int],
    default_num_params: int = 17,
) -> list[dict]:
    """parts_by_no: part_no -> (drawing_rev, part_id or None)"""
    out = []
    for r in rows:
        row = dict(r)
        part_no = str(row.get("Part Number", "")).strip()
        draw_rev, part_id = parts_by_no.get(part_no, (None, None))
        row["draw_rev"] = draw_rev or ""
        try:
            qty_val = float(row.get("Quantity") or 0)
        except (TypeError, ValueError):
            qty_val = 0
        row["sample_size"] = sample_size_for_quantity(qty_val)
        if part_id is not None:
            row["num_params"] = param_count_by_part_id.get(part_id, default_num_params)
        else:
            row["num_params"] = default_num_params
        out.append(row)
    return out
