"""Tests for parameter-based Method of Inspection normalization."""

from __future__ import annotations

from app.moi_normalization import (
    infer_moi_qti_from_parameter,
    normalize_ad_row,
    normalize_method_of_inspection,
)


def test_diameter_width_od_id_map_to_dvc():
    assert infer_moi_qti_from_parameter("2 HOLES DIA") == "DVC"
    assert infer_moi_qti_from_parameter("Overall Width") == "DVC"
    assert infer_moi_qti_from_parameter("Shaft OD") == "DVC"
    assert infer_moi_qti_from_parameter("Bore ID") == "DVC"


def test_thickness_maps_to_dmm():
    assert infer_moi_qti_from_parameter("Plate Thickness") == "DMM"
    assert infer_moi_qti_from_parameter("THK") == "DMM"


def test_radius_angle_thread_dft():
    assert infer_moi_qti_from_parameter("Corner Radius") == "RG"
    assert infer_moi_qti_from_parameter("Bevel Angle") == "BP"
    assert infer_moi_qti_from_parameter("M10 Thread") == "TPG"
    assert infer_moi_qti_from_parameter("M6") == "TPG"
    assert infer_moi_qti_from_parameter("Tapped Hole", "M8X1.25") == "TPG"
    assert normalize_method_of_inspection("Hole Dia", "M10X1.5", None, "DVC") == "TPG"


def test_thread_moi_aliases():
    assert normalize_method_of_inspection("M6", None, None, "TG") == "TPG"
    assert normalize_method_of_inspection("M6", None, None, "M6 TG") == "TPG"
    assert normalize_method_of_inspection("M12", None, None, "DVC") == "TPG"
    assert normalize_method_of_inspection("Nut", None, None, "TG") == "TPG"
    assert infer_moi_qti_from_parameter("DFT") == "DFT"


def test_pitch_hole_ref_location_coords_critical():
    assert infer_moi_qti_from_parameter("Hole pitch") == "DHG"
    assert infer_moi_qti_from_parameter("Hole Centre") == "DHG"
    assert infer_moi_qti_from_parameter("Hole Reference") == "DHG"
    assert infer_moi_qti_from_parameter("X Coordinate") == "DHG"
    assert infer_moi_qti_from_parameter("Y Coordinates") == "DHG"
    assert infer_moi_qti_from_parameter("Location A") == "DHG"
    assert infer_moi_qti_from_parameter("Ref Dimension") == "DHG"
    assert infer_moi_qti_from_parameter("Width", special_char="C") == "DHG"


def test_parameter_inference_overrides_raw_moi():
    assert (
        normalize_method_of_inspection(
            "2 HOLES DIA",
            "20.5+0.5",
            None,
            "Vernier Height Gauge",
        )
        == "DVC"
    )
    assert (
        normalize_method_of_inspection(
            "Hole pitch",
            "200±0.25",
            None,
            "Vernier Caliper",
        )
        == "DHG"
    )


def test_raw_moi_fallback_when_parameter_unmatched():
    assert normalize_method_of_inspection("Visual Check", None, None, "Visual Inspection") == "VIS"
    assert normalize_method_of_inspection("Coating", "60±10 Micron", None, "DFT METER") == "DFT"


def test_dft_from_special_char_when_moi_empty():
    assert normalize_method_of_inspection("Black Powder Coating", None, "DFT METER", None) == "DFT"


def test_normalize_ad_row():
    row = normalize_ad_row(
        {
            "parameter": "DFT",
            "specification": "60±10 Micron",
            "special_char": None,
            "method_of_inspection": "DFT METER",
        }
    )
    assert row["method_of_inspection"] == "DFT"
