"""
Part master Method of Inspection normalization on import/edit.

1. Identify expected MOI from specification (and parameter context).

2. Auto-correct when the row is NOT Pitch / Hole Ref / Hole Center / Dimension / Height,
   and the specification indicates:
     Thread → TPG, Radius → RG, Thickness → DMM,
     Diameter → DVC, DFT → DFT METER, Visual → VIS

3. For Pitch, Hole Ref, Hole Center, Dimension, Height parameters:
   do not auto-correct — only standardize MOI name aliases (e.g. Vernier Hight Guage → DHG).
"""

from __future__ import annotations

import re
from typing import Any

_THREAD_SIZE = re.compile(r"\bM(?:6|8|10|12)\b", re.I)
_THREAD_DESIGNATION = re.compile(r"\bM\d+(?:\.\d+)?\s*[X×]\d+(?:\.\d+)?\b", re.I)
_THREAD_DESIGNATION_COMPACT = re.compile(r"^M\d+(?:\.\d+)?[X×]\d+(?:\.\d+)?$", re.I)

_NO_AUTO_CORRECT_PARAM = re.compile(
    r"\bPITCH\b|"
    r"\bHOLE\s*REF(?:ERENCE)?\b|"
    r"\bHOLE\s*(?:CENTRE|CENTER)\b|"
    r"\bDIMENSION\b|"
    r"\bHEIGHT\b|\bHIGHT\b|\bHIEGHT\b",
    re.I,
)

# Specification patterns for auto-correct (checked in priority order).
_SPEC_VISUAL = re.compile(
    r"\bNOT\s+ALLOWED\b|\bNOT\s+PERMITTED\b|\bNO\s+DEFECT\b|\bFREE\s+FROM\b|\bSHALL\s+BE\s+FREE\b",
    re.I,
)
_SPEC_DIAMETER = re.compile(r"[Ø∅Φ]|(?:\bDIA\.?\b|\bDIAMETER\b)", re.I)
_SPEC_DIAMETER_NUMERIC = re.compile(
    r"^\s*\d+(?:\.\d+)?\s*(?:[\+\-±]|\+|\-|\±)\s*\d",
    re.I,
)
_SPEC_RADIUS = re.compile(r"(?:\bRADIUS\b|\bRAD\b|\bR\s*\d|\bR\d+(?:\.\d+)?\b)", re.I)
_SPEC_DFT = re.compile(r"\b(?:MICRON|MICRONS|µM|UM)\b|\bDFT\b", re.I)
_SPEC_THICKNESS_PARAM = re.compile(r"\bTHICKNESS\b|\bTHK\b|\bTHICK\b", re.I)
_SPEC_DIAMETER_PARAM = re.compile(
    r"\bDIA\b|\bDIAM\b|\bDIAMETER\b|\bWIDTH\b|\bOD\b|\bID\b|\bO\.?\s*D\.?\b|\bI\.?\s*D\.?\b",
    re.I,
)
_SPEC_VISUAL_PARAM = re.compile(
    r"\bVISUAL\b|\bRUST\b|\bDENT\b|\bDAMAGE\b|\bSCORING\b|\bWELD\b|\bBURR\b|\bAPPEARANCE\b",
    re.I,
)
_QR_CODE_PARAM = re.compile(r"\bQR\s*CODE\b", re.I)
_FLATNESS_PARAM = re.compile(r"\b(?:FLATNESS|FLATENESS)\b", re.I)
_PARALLEL_PARAM = re.compile(r"\bPARALLEL(?:ISM)?\b", re.I)


def is_qr_code_parameter(parameter: str | None) -> bool:
    """True when parameter denotes QR code verification (e.g. QR code MISS MATCH)."""
    return bool(_QR_CODE_PARAM.search(_norm_key(parameter)))


def is_flatness_parameter(parameter: str | None) -> bool:
    return bool(_FLATNESS_PARAM.search(_norm_key(parameter)))


def is_parallelism_parameter(parameter: str | None) -> bool:
    return bool(_PARALLEL_PARAM.search(_norm_key(parameter)))


def moi_for_gdt_shop_gauge_parameter(parameter: str | None) -> str | None:
    """Flatness → Feeler gauge; Parallel / Parallelism → Parallel gauge."""
    if is_flatness_parameter(parameter):
        return "Feeler gauge (FG)"
    if is_parallelism_parameter(parameter):
        return "PARALLEL GAUGE"
    return None


def _norm_key(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().upper())


def is_no_auto_correct_parameter(parameter: str | None) -> bool:
    """Pitch, Hole Ref/Center, Dimension, Height — standardize MOI names only."""
    return bool(_NO_AUTO_CORRECT_PARAM.search(_norm_key(parameter)))


def looks_like_thread_specification(
    parameter: str | None,
    specification: str | None,
) -> bool:
    """True when parameter or specification denotes a metric thread (M6/M8/M10/M12 or M#X#)."""
    param = _norm_key(parameter)
    if param and _THREAD_SIZE.search(param):
        return True
    if param and _THREAD_DESIGNATION.search(param):
        return True
    for text in (parameter, specification):
        if not text:
            continue
        compact = re.sub(r"\s+", "", _norm_key(text))
        if _THREAD_DESIGNATION_COMPACT.match(compact):
            return True
    return False


def _standardize_moi_name(raw: str | None) -> str | None:
    """Map raw MOI spellings to canonical QTI names without inferring from parameter/spec."""
    s = _norm_key(raw)
    if not s:
        return None

    if s in {"VISUAL", "VISUAL INSPECTION", "VISUVAL"} or (s == "VISUAL"):
        return "VIS"
    if "VISUAL" in s and len(s) < 40:
        return "VIS"

    if s in {"DFT", "DFT METER", "DFT METRE"} or (s.startswith("DFT ") and "METER" in s):
        return "DFT METER"

    if re.match(r"^(?:M(?:6|8|10|12)\s*)?(?:TG|TPG)$", s):
        return "TPG"
    if s in {"TG", "THREAD PLUG GAUGE", "THREAD PLUG GUAGE", "THREAD GAUGE", "THREAD GUAGE"}:
        return "TPG"
    if "THREAD PLUG" in s or "THREAD GAUGE" in s or "GO AND NO GO THREAD" in s:
        return "TPG"

    if s in {"DHG", "DHI", "VHG", "V.H.G", "V.H.G.", "DGH"}:
        return "DHG"
    if re.search(r"HEIGHT\s*(GAU|GAGE|GUAGE)|HIEGHT|HIGHT\s*GU", s):
        return "DHG"
    if "VERNIER HEIGHT" in s or "VENIRE HEIGHT" in s or "VENIRE HIGHT" in s:
        return "DHG"

    if s in {"DVC", "VC", "V.C", "V.C."}:
        return "DVC"
    if re.search(r"VERNIER|VENIRE|VERNNIER|CALLIPER|CALIPER|CALPER|CALIPPER", s):
        if "HEIGHT" in s or "HIGHT" in s or "HIEGHT" in s:
            return "DHG"
        return "DVC"

    if re.match(r"^(MIC|MM|DMM|MICRO\s*METER|MICROMETER|MICRO\s*METRE)$", s.replace(".", "")):
        return "DMM"
    if "MICROMETER" in s or "MICROMET" in s or s.startswith("MIC ") or s == "MIC":
        return "DMM"

    if s in {"RG", "R.G", "R.G."} or ("RADIUS" in s and "GAU" in s):
        return "RG"

    if s in {"BP", "BEVEL", "B.P", "B.P."} or "PROTRACTOR" in s or "PROTECTOR" in s:
        return "BP"

    if s in {"QRS", "QR SCAN", "QR SCANNER"} or (s.startswith("QR") and "SCAN" in s):
        return "QR SCANNER"

    if "FEELER" in s or s == "FG":
        return "Feeler gauge (FG)"

    if "PARALLEL" in s and "GAU" in s:
        return "PARALLEL GAUGE"

    if s in {
        "TPG",
        "DVC",
        "DMM",
        "RG",
        "BP",
        "DHG",
        "VIS",
        "DFT METER",
        "CMM",
        "CG",
        "QR SCANNER",
        "Feeler gauge (FG)",
        "FG",
        "PARALLEL GAUGE",
    }:
        return s if s != "FG" else "Feeler gauge (FG)"

    return None


def expected_moi_from_specification(
    parameter: str | None,
    specification: str | None,
) -> str | None:
    """
    Infer expected MOI from specification (and parameter when needed).
    Used only for auto-correct rows.
    """
    param = _norm_key(parameter)
    spec = (specification or "").strip()
    spec_u = _norm_key(specification)

    if is_qr_code_parameter(parameter):
        return "QR SCANNER"

    gdt_moi = moi_for_gdt_shop_gauge_parameter(parameter)
    if gdt_moi:
        return gdt_moi

    spec_compact = re.sub(r"\s+", "", spec_u)

    if _SPEC_VISUAL_PARAM.search(param) or (spec_u and _SPEC_VISUAL.search(spec_u)):
        return "VIS"

    if looks_like_thread_specification(parameter, specification):
        return "TPG"

    if param and re.search(r"\bDFT\b", param):
        return "DFT METER"
    if spec_u and _SPEC_DFT.search(spec_u):
        return "DFT METER"

    if spec_u and _SPEC_RADIUS.search(spec_u):
        return "RG"
    if param and re.search(r"\bRADIUS\b|\bRAD\b", param):
        return "RG"

    if param and _SPEC_THICKNESS_PARAM.search(param) and spec_u:
        return "DMM"

    if spec and (_SPEC_DIAMETER.search(spec) or _SPEC_DIAMETER_NUMERIC.match(spec)):
        return "DVC"
    if param and _SPEC_DIAMETER_PARAM.search(param) and spec_u:
        return "DVC"

    return None


def normalize_part_master_moi(
    parameter: str | None,
    specification: str | None = None,
    special_char: str | None = None,
    raw_moi: str | None = None,
) -> str | None:
    """Normalize MOI for a spec / CCP / coating row."""
    _ = special_char

    if is_qr_code_parameter(parameter):
        return "QR SCANNER"

    gdt_moi = moi_for_gdt_shop_gauge_parameter(parameter)
    if gdt_moi:
        return gdt_moi

    if is_no_auto_correct_parameter(parameter):
        standardized = _standardize_moi_name(raw_moi)
        raw = (raw_moi or "").strip()
        return standardized or raw or None

    expected = expected_moi_from_specification(parameter, specification)
    if expected:
        return expected

    standardized = _standardize_moi_name(raw_moi)
    if standardized:
        return standardized

    raw = (raw_moi or "").strip()
    return raw or None


# Backward-compatible aliases
normalize_thread_method_of_inspection = normalize_part_master_moi


def infer_moi_from_parameter(parameter: str | None) -> str | None:
    """Legacy helper: expected MOI when treating parameter as auto-correct context."""
    if is_no_auto_correct_parameter(parameter):
        return None
    return expected_moi_from_specification(parameter, None)


def normalize_ad_row_moi(row: dict[str, Any]) -> dict[str, Any]:
    """Apply MOI normalization to one A/B/D-style row dict."""
    moi = normalize_part_master_moi(
        row.get("parameter"),
        row.get("specification"),
        row.get("special_char"),
        row.get("method_of_inspection"),
    )
    return {**row, "method_of_inspection": moi}


def normalize_bundle_part_master_moi(bundle: dict[str, Any]) -> dict[str, Any]:
    """Apply MOI normalization to all spec / CCP / coating rows in a bundle."""
    for part in bundle.get("parts") or []:
        for key in ("spec_rows", "ccp_rows", "coating_rows"):
            part[key] = [normalize_ad_row_moi(r) for r in part.get(key) or []]
    return bundle


normalize_ad_row_thread_moi = normalize_ad_row_moi
normalize_bundle_thread_moi = normalize_bundle_part_master_moi
