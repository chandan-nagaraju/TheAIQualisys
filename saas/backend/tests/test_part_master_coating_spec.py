"""Tests for Section D plating thickness specification normalization."""

from __future__ import annotations

from app.part_master_coating_spec import (
    is_plating_thickness_row,
    normalize_plating_thickness_specification,
    parse_plating_thickness_spec,
)



def test_plating_thickness_row_detection():
    assert is_plating_thickness_row("PLATING THICKNESS", "Min 12 micron")
    assert is_plating_thickness_row("DFT", "60±10 Micron")
    assert not is_plating_thickness_row("Black Powder Coating", "BLACK")


def test_parse_explicit_micron_range():
    band = parse_plating_thickness_spec("8 – 12 µm")
    assert band is not None
    assert band.min_um == 8
    assert band.max_um == 12

    band2 = parse_plating_thickness_spec("8-12 micron")
    assert band2 is not None
    assert band2.min_um == 8
    assert band2.max_um == 12


def test_parse_symmetric_micron_tolerance():
    band = parse_plating_thickness_spec("10 ± 2 µm")
    assert band is not None
    assert band.min_um == 8
    assert band.max_um == 12
    assert band.nominal_um == 10
    assert band.tolerance_um == 2


def test_min_only_micron_rewritten_to_band():
    assert normalize_plating_thickness_specification("PLATING THICKNESS", "Min 12 micron") == "8 – 12 µm"
    assert normalize_plating_thickness_specification("PLATING THICKNESS", "Min 12 Micron") == "8 – 12 µm"


def test_pm_form_kept_for_symmetric_tolerance():
    assert normalize_plating_thickness_specification("DFT", "10 ± 2 µm") == "10 ± 2 µm"
    assert normalize_plating_thickness_specification("DFT", "60±10 Micron") == "60 ± 10 µm"


def test_range_form_kept():
    assert normalize_plating_thickness_specification("PLATING THICKNESS", "8 – 12 µm") == "8 – 12 µm"


def test_min_only_mic_abbreviation_rewritten():
    assert normalize_plating_thickness_specification("Plating thickness", "Min 12 mic") == "8 – 12 µm"
    assert normalize_plating_thickness_specification("PLATING THICKNESS", "Min 12 mic") == "8 – 12 µm"


def test_plating_thickness_moi_is_dft_meter():
    from app.part_master_moi import normalize_part_master_moi

    assert normalize_part_master_moi("Plating thickness", "Min 12 mic", None, "DMM") == "DFT METER"
    assert normalize_part_master_moi("Plating thickness", "Min 12 mic", None, "Micrometer") == "DFT METER"


def test_excel_import_normalizes_plating_min_spec():
    import io

    import pandas as pd

    from app.fir_part_excel import parse_parts_excel_to_bundle_dict

    grid = [
        ["PART NO", "FS465913", "", "DESCRIPTION", "LINK ROD"],
        ["D) Surface Coating", "", "", "", ""],
        ["Parameter", "Specification", "Special Char", "Method", ""],
        ["PLATING THICKNESS", "Min 12 micron", "", "DFT METER", ""],
    ]
    max_cols = max(len(r) for r in grid)
    padded = [r + [""] * (max_cols - len(r)) for r in grid]
    df = pd.DataFrame(padded)
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="FIR", index=False, header=False)
    bundle = parse_parts_excel_to_bundle_dict(bio.getvalue(), source_filename="FS465913.xlsx")
    part = bundle["parts"][0]
    assert part["coating_rows"][0]["specification"] == "8 – 12 µm"
    assert part["coating_rows"][0]["method_of_inspection"] == "DFT METER"

    band = parse_plating_thickness_spec("8 – 12 µm")
    assert band is not None

    def ok(v: float) -> bool:
        return band.min_um <= v <= band.max_um

    assert not ok(7.5)
    assert ok(8.0)
    assert ok(10.2)
    assert ok(11.8)
    assert ok(12.0)
    assert not ok(12.5)
