"""Tests for TPG-only thread Method of Inspection normalization."""

from __future__ import annotations

import io

import pandas as pd

from app.fir_part_excel import parse_parts_excel_to_bundle_dict
from app.thread_moi import (
    looks_like_thread_specification,
    normalize_thread_method_of_inspection,
)


def test_thread_sizes_and_designations():
    assert looks_like_thread_specification("M6", None)
    assert looks_like_thread_specification("M10 Thread", None)
    assert looks_like_thread_specification("Tapped Hole", "M8X1.25")
    assert not looks_like_thread_specification("2 HOLES DIA", "20.5+0.5")


def test_tg_and_m6_tg_map_to_tpg():
    assert normalize_thread_method_of_inspection("M6", None, None, "TG") == "TPG"
    assert normalize_thread_method_of_inspection("M6", None, None, "M6 TG") == "TPG"
    assert normalize_thread_method_of_inspection("Nut", None, None, "TG") == "TPG"


def test_thread_spec_overrides_dvc():
    assert normalize_thread_method_of_inspection("M12", None, None, "DVC") == "TPG"
    assert normalize_thread_method_of_inspection("Hole", "M10X1.5", None, "DVC") == "TPG"


def test_non_thread_moi_unchanged():
    assert normalize_thread_method_of_inspection("2 HOLES DIA", "20.5+0.5", None, "DVC") == "DVC"
    assert normalize_thread_method_of_inspection("Ref Dimension", "7±0.5", "C", "DHG") == "DHG"
    assert normalize_thread_method_of_inspection("DFT", "60±10 Micron", None, "DFT METER") == "DFT METER"


def test_excel_import_normalizes_thread_moi_only():
    grid = [
        ["PART NO", "FS465913", "", "DESCRIPTION", "LINK ROD"],
        ["A) Dimension Parameters", "", "", "", ""],
        ["Parameter", "Specification (mm)", "Special Characteristics", "Method of Inspection", ""],
        ["2 HOLES DIA", "20.5+0.5", "", "DVC", ""],
        ["M6", "M6X1.0", "", "TG", ""],
        ["D) Surface Coating", "", "", "", ""],
        ["Parameter", "Specification", "Special Char", "Method", ""],
        ["DFT", "60±10 Micron", "", "DFT METER", ""],
    ]
    max_cols = max(len(r) for r in grid)
    padded = [r + [""] * (max_cols - len(r)) for r in grid]
    df = pd.DataFrame(padded)
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="FIR", index=False, header=False)
    bundle = parse_parts_excel_to_bundle_dict(bio.getvalue(), source_filename="FS465913.xlsx")
    part = bundle["parts"][0]
    assert part["spec_rows"][0]["method_of_inspection"] == "DVC"
    assert part["spec_rows"][1]["method_of_inspection"] == "TPG"
    assert part["coating_rows"][0]["method_of_inspection"] == "DFT METER"
