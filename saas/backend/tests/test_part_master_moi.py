"""Tests for specification-based part master MOI normalization."""

from __future__ import annotations

import io

import pandas as pd

from app.fir_part_excel import parse_parts_excel_to_bundle_dict
from app.part_master_moi import (
    expected_moi_from_specification,
    is_no_auto_correct_parameter,
    looks_like_thread_specification,
    normalize_part_master_moi,
)


def test_no_auto_correct_parameters():
    assert is_no_auto_correct_parameter("HOLE PITCH")
    assert is_no_auto_correct_parameter("Hole Ref")
    assert is_no_auto_correct_parameter("Hole Centre")
    assert is_no_auto_correct_parameter("DIMENSION")
    assert is_no_auto_correct_parameter("BUSH HEIGHT")
    assert is_no_auto_correct_parameter("Ref Dimension")
    assert not is_no_auto_correct_parameter("4 HOLE DIAMETER")


def test_auto_correct_from_specification():
    assert expected_moi_from_specification("4 HOLE DIAMETER", "Ø8.5 - 0.2") == "DVC"
    assert expected_moi_from_specification("2 HOLES DIA", "20.5+0.5") == "DVC"
    assert expected_moi_from_specification("Plate Thickness", "12±0.5") == "DMM"
    assert expected_moi_from_specification("Corner", "R5 MAX") == "RG"
    assert expected_moi_from_specification("M6", "M6X1.0") == "TPG"
    assert expected_moi_from_specification("DFT", "60±10 Micron") == "DFT METER"
    assert expected_moi_from_specification("RUST/DENT", "NOT ALLOWED") == "VIS"
    # Numeric spec alone looks dimensional; pitch rows skip auto-correct in normalize_part_master_moi.
    assert expected_moi_from_specification("HOLE PITCH", "18.4 ± 0.3") == "DVC"


def test_auto_correct_overrides_raw_moi():
    assert normalize_part_master_moi("4 HOLE DIAMETER", "Ø8.5 - 0.2", None, "Vernier Caliper") == "DVC"
    assert normalize_part_master_moi("2 HOLES DIA", "20.5+0.5", None, "Vernier Height Gauge") == "DVC"
    assert normalize_part_master_moi("Plate Thickness", "12±0.5", None, "Micrometer") == "DMM"
    assert normalize_part_master_moi("M6", "M6X1.0", None, "TG") == "TPG"
    assert normalize_part_master_moi("DFT", "60±10 Micron", None, "DFT") == "DFT METER"
    assert normalize_part_master_moi("RUST/DENT & DAMAGES/", "NOT ALLOWED", None, "Visual") == "VIS"


def test_qr_code_parameter_maps_to_qr_scanner():
    from app.part_master_moi import is_qr_code_parameter

    assert is_qr_code_parameter("QR code MISS MATCH")
    assert normalize_part_master_moi("QR code MISS MATCH", "NOT ALLOWED", None, "VIS") == "QR SCANNER"
    assert normalize_part_master_moi("QR code MISS MATCH", "NOT ALLOWED", None, None) == "QR SCANNER"
    assert expected_moi_from_specification("QR code MISS MATCH", "NOT ALLOWED") == "QR SCANNER"


def test_flatness_parallel_perpendicular_gdt_parameters():
    assert normalize_part_master_moi("FLATNESS", "0.5", None, "DVC") == "Feeler gauge (FG)"
    assert normalize_part_master_moi("FLATENESS", "0.5", None, "DVC") == "Feeler gauge (FG)"
    assert normalize_part_master_moi("FLATNESS", "0.5", None, "DHG") == "DHG"
    assert normalize_part_master_moi("PARALLEL", "1", None, "DVC") == "PARALLEL GAUGE"
    assert normalize_part_master_moi("PARALLELISM", "1 MAX", None, "DHG") == "DHG"
    assert normalize_part_master_moi("PARALLEL", "1", None, "VHG") == "DHG"
    assert normalize_part_master_moi("PARALLELISM", "1", None, "HG") == "DHG"
    assert normalize_part_master_moi("PARALLEL", "1", None, "Digital Height Gauge") == "DHG"
    assert normalize_part_master_moi("PERPENDICULARITY", "0.05", None, "DVC") == "PERPENDICULAR GAUGE"
    assert normalize_part_master_moi("PERPENDICULAR", "0.1", None, "DVC") == "PERPENDICULAR GAUGE"
    assert normalize_part_master_moi("PERPENDIVULARITY", "0.1", None, "DVC") == "PERPENDICULAR GAUGE"
    assert normalize_part_master_moi("PERPENDICULARITY", "0.05", None, "DHG") == "DHG"
    assert normalize_part_master_moi("PERPENDICULARITY", "0.05", None, "VHG") == "DHG"
    assert expected_moi_from_specification("FLATNESS", "0.5") == "Feeler gauge (FG)"
    assert expected_moi_from_specification("FLATENESS", "0.5") == "Feeler gauge (FG)"
    assert expected_moi_from_specification("PARALLEL", "1") == "PARALLEL GAUGE"
    assert expected_moi_from_specification("PERPENDICULARITY", "0.05") == "PERPENDICULAR GAUGE"


def test_no_auto_correct_only_standardizes_names():
    assert (
        normalize_part_master_moi("HOLE PITCH", "18.4 ± 0.3", None, "Vernier Hight Guage") == "DHG"
    )
    assert normalize_part_master_moi("BUSH HEIGHT", "15.-0.3", None, "Vernier Caliper") == "DVC"
    assert normalize_part_master_moi("DIMENSION", "47.5+0.5", None, "Vernier Hight Guage") == "DHG"
    assert normalize_part_master_moi("Ref Dimension", "7±0.5", "C", "DHG") == "DHG"
    assert normalize_part_master_moi("Hole Centre", "10±0.1", None, "Vernier Height Gauge") == "DHG"


def test_pitch_does_not_auto_correct_to_dvc_from_numeric_spec():
    """Numeric pitch spec must not force DVC even though it looks dimensional."""
    assert normalize_part_master_moi("HOLE PITCH", "18.4 ± 0.3", None, "Vernier Caliper") == "DVC"


def test_thread_sizes_and_designations():
    assert looks_like_thread_specification("M6", None)
    assert looks_like_thread_specification("Tapped Hole", "M8X1.25")
    assert not looks_like_thread_specification("2 HOLES DIA", "20.5+0.5")


def test_excel_import_applies_rules():
    grid = [
        ["PART NO", "FS465913", "", "DESCRIPTION", "LINK ROD"],
        ["A) Dimension Parameters", "", "", "", ""],
        ["Parameter", "Specification (mm)", "Special Characteristics", "Method of Inspection", ""],
        ["4 HOLE DIAMETER", "Ø8.5 - 0.2", "", "Vernier Caliper", ""],
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
    assert part["spec_rows"][2]["method_of_inspection"] == "DHG"
    assert part["spec_rows"][3]["method_of_inspection"] == "TPG"
    assert part["coating_rows"][0]["method_of_inspection"] == "DFT METER"
