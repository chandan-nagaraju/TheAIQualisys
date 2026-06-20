"""Tests for scoped part master MOI normalization (DVC, DMM, RG, BP, TPG only)."""

from __future__ import annotations

import io

import pandas as pd

from app.fir_part_excel import parse_parts_excel_to_bundle_dict
from app.part_master_moi import (
    infer_moi_from_parameter,
    looks_like_thread_specification,
    normalize_part_master_moi,
)


def test_thread_sizes_and_designations():
    assert looks_like_thread_specification("M6", None)
    assert looks_like_thread_specification("M10 Thread", None)
    assert looks_like_thread_specification("Tapped Hole", "M8X1.25")
    assert not looks_like_thread_specification("2 HOLES DIA", "20.5+0.5")


def test_parameter_dvc_dmm_rg_bp():
    assert infer_moi_from_parameter("2 HOLES DIA") == "DVC"
    assert infer_moi_from_parameter("4 HOLE DIAMETER") == "DVC"
    assert infer_moi_from_parameter("Overall Width") == "DVC"
    assert infer_moi_from_parameter("Shaft OD") == "DVC"
    assert infer_moi_from_parameter("Bore ID") == "DVC"
    assert infer_moi_from_parameter("Plate Thickness") == "DMM"
    assert infer_moi_from_parameter("THK") == "DMM"
    assert infer_moi_from_parameter("Corner Radius") == "RG"
    assert infer_moi_from_parameter("Bevel Angle") == "BP"
    assert infer_moi_from_parameter("HOLE PITCH") is None


def test_parameter_inference_overrides_raw_moi():
    assert normalize_part_master_moi("2 HOLES DIA", "20.5+0.5", None, "Vernier Caliper") == "DVC"
    assert normalize_part_master_moi("4 HOLE DIAMETER", "Ø8.5 - 0.2", None, "Vernier Caliper") == "DVC"
    assert normalize_part_master_moi("Plate Thickness", "12±0.5", None, "Micrometer") == "DMM"
    assert normalize_part_master_moi("Corner Radius", "R5", None, "Radius Gauge") == "RG"
    assert normalize_part_master_moi("Bevel Angle", "45°", None, "Bevel Protractor") == "BP"


def test_tg_and_m6_tg_map_to_tpg():
    assert normalize_part_master_moi("M6", None, None, "TG") == "TPG"
    assert normalize_part_master_moi("M6", None, None, "M6 TG") == "TPG"
    assert normalize_part_master_moi("Nut", None, None, "TG") == "TPG"


def test_thread_spec_overrides_dvc():
    assert normalize_part_master_moi("M12", None, None, "DVC") == "TPG"
    assert normalize_part_master_moi("Hole", "M10X1.5", None, "DVC") == "TPG"


def test_dft_parameter_maps_to_dft_meter():
    assert infer_moi_from_parameter("DFT") == "DFT METER"
    assert normalize_part_master_moi("DFT", "60±10 Micron", None, "DFT METER") == "DFT METER"
    assert normalize_part_master_moi("DFT", "60±10 Micron", None, "DFT") == "DFT METER"
    assert normalize_part_master_moi("DFT", "60±10 Micron", None, None) == "DFT METER"


def test_out_of_scope_moi_unchanged():
    assert (
        normalize_part_master_moi("HOLE PITCH", "18.4 ± 0.3", None, "Vernier Hight Guage")
        == "Vernier Hight Guage"
    )
    assert normalize_part_master_moi("BUSH HEIGHT", "15.-0.3", None, "Vernier Caliper") == "Vernier Caliper"
    assert (
        normalize_part_master_moi("RUST/DENT & DAMAGES/", "NOT ALLOWED", None, "Visual") == "Visual"
    )
    assert normalize_part_master_moi("Ref Dimension", "7±0.5", "C", "DHG") == "DHG"


def test_excel_import_normalizes_scoped_rules_only():
    grid = [
        ["PART NO", "FS465913", "", "DESCRIPTION", "LINK ROD"],
        ["A) Dimension Parameters", "", "", "", ""],
        ["Parameter", "Specification (mm)", "Special Characteristics", "Method of Inspection", ""],
        ["2 HOLES DIA", "20.5+0.5", "", "Vernier Caliper", ""],
        ["Plate Thickness", "12±0.5", "", "Micrometer", ""],
        ["Hole pitch", "200±0.25", "", "Vernier Height Gauge", ""],
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
    assert part["spec_rows"][1]["method_of_inspection"] == "DMM"
    assert part["spec_rows"][2]["method_of_inspection"] == "Vernier Height Gauge"
    assert part["spec_rows"][3]["method_of_inspection"] == "TPG"
    assert part["coating_rows"][0]["method_of_inspection"] == "DFT METER"
