"""Loose single-sheet FIR Excel parsing (sections A–D)."""

from __future__ import annotations

import io

import pandas as pd
import pytest

from app.fir_part_excel import (
    _ad_row_from_loose_row_vals,
    _parse_loose_ad_table,
    _scan_section_b_rows,
    _scan_section_d_rows,
    parse_parts_excel_to_bundle_dict,
)


def _df_from_grid(rows: list[list[str]]) -> pd.DataFrame:
    max_cols = max(len(r) for r in rows)
    padded = [r + [""] * (max_cols - len(r)) for r in rows]
    return pd.DataFrame(padded)


def test_dft_meter_goes_to_method_not_special_char():
    row = _ad_row_from_loose_row_vals(["1", "DFT", "60±10 Micron", "DFT METER"])
    assert row is not None
    assert row["parameter"] == "DFT"
    assert row["specification"] == "60±10 Micron"
    assert row["special_char"] is None
    assert row["method_of_inspection"] == "DFT METER"


def test_loose_fir_sections_a_b_d():
    grid = [
        ["PART NO", "FS465913", "", "DESCRIPTION", "LINK ROD PLATE"],
        ["DRAW.REV NO", "#2", "", "", ""],
        ["A) Dimension Parameters", "", "", "", ""],
        ["Sl No", "Parameter", "Specification (mm)", "Special Characteristics", "Method of Inspection"],
        ["1", "2 HOLES DIA", "20.5+0.5", "", "Vernier Caliper"],
        ["2", "Hole pitch", "200±0.25", "", "Vernier Height Gauge"],
        ["", "", "", "", ""],
        ["", "", "", "", ""],
        ["", "", "", "", ""],
        ["", "", "", "", ""],
        ["", "", "", "", ""],
        ["", "", "", "", ""],
        ["B) Customer End Complaints Parameters & Check points", "", "", "", ""],
        ["(All CPI Issues to be covered and measured 100%)", "", "", "", ""],
        ["Sl No", "Parameter", "Specification (mm)", "Special Characteristics", "Method of Inspection"],
        ["1", "Ref Dimension", "7±0.5", "C", "DHG"],
        ["C) Material Grade", "", "", "", ""],
        ["1", "BSK46", "", "", ""],
        ["D) Surface Coating", "", "", "", ""],
        ["Sl No", "Parameter", "Specification", "Special Char", "Method"],
        ["1", "DFT", "60±10 Micron", "", "DFT METER"],
        ["2", "Black Powder Coating", "", "", ""],
    ]
    df = _df_from_grid(grid)

    a_rows = _parse_loose_ad_table(df, start_row=0, end_row=_find_b(df))
    b_rows = _scan_section_b_rows(df)
    d_rows = _scan_section_d_rows(df)

    assert len(a_rows) == 2
    assert a_rows[0]["parameter"] == "2 HOLES DIA"
    assert len(b_rows) == 1
    assert b_rows[0]["parameter"] == "Ref Dimension"
    assert b_rows[0]["specification"] == "7±0.5"
    assert b_rows[0]["method_of_inspection"] == "DHG"
    assert len(d_rows) == 2
    assert d_rows[0]["parameter"] == "DFT"
    assert d_rows[0]["method_of_inspection"] == "DFT METER"
    assert d_rows[0]["special_char"] is None


def _find_b(df: pd.DataFrame) -> int:
    from app.fir_part_excel import _find_section_anchor_row

    return _find_section_anchor_row(df, "b") or 0


def test_loose_workbook_bundle_includes_section_b():
    grid = [
        ["PART NO", "FS465913", "", "DESCRIPTION", "LINK ROD"],
        ["A) Dimension Parameters", "", "", "", ""],
        ["Parameter", "Specification (mm)", "Special Characteristics", "Method of Inspection", ""],
        ["2 HOLES DIA", "20.5+0.5", "", "Vernier Caliper", ""],
        ["B) Customer End Complaints Parameters", "", "", "", ""],
        ["Parameter", "Specification (mm)", "Special Characteristics", "Method of Inspection", ""],
        ["Ref Dimension", "7±0.5", "", "DHG", ""],
        ["C) Material Grade", "", "", "", ""],
        ["BSK46", "", "", "", ""],
        ["D) Surface Coating", "", "", "", ""],
        ["Parameter", "Specification", "Special Char", "Method", ""],
        ["DFT", "60±10 Micron", "", "DFT METER", ""],
    ]
    df = _df_from_grid(grid)
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="FIR", index=False, header=False)
    bundle = parse_parts_excel_to_bundle_dict(bio.getvalue(), source_filename="FS465913.xlsx")
    assert len(bundle["parts"]) == 1
    part = bundle["parts"][0]
    assert part["part"]["part_no"] == "FS465913"
    assert len(part["spec_rows"]) >= 1
    assert len(part["ccp_rows"]) == 1
    assert part["ccp_rows"][0]["parameter"] == "Ref Dimension"
    assert part["coating_rows"][0]["method_of_inspection"] == "DFT METER"
    assert part["coating_rows"][0]["special_char"] is None
