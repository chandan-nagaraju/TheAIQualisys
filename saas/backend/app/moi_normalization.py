"""
Normalize Method of Inspection (MOI) to QTI instrument codes on part master import.

Primary rule: infer MOI from parameter name (and related row context). When parameter
does not match a known pattern, fall back to normalizing the raw MOI string.
"""

from __future__ import annotations

import re
from typing import Any

# Parameter-name patterns → QTI code (order matters: more specific first).
_PARAM_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bDFT\b", re.I), "DFT"),
    (re.compile(r"\bTHREAD\b|\bTPI\b|\bT\.?\s*PI\b", re.I), "TPG"),
    (re.compile(r"\bTHICKNESS\b|\bTHK\b|\bTHICK\b", re.I), "DMM"),
    (re.compile(r"\bRADIUS\b|\bRAD\b", re.I), "RG"),
    (re.compile(r"\bANGLE\b|\bBEVEL\b", re.I), "BP"),
    (
        re.compile(
            r"\bDIA\b|\bDIAM\b|\bDIAMETER\b|\bWIDTH\b|\bW\b|\bOD\b|\bID\b|\bO\.?\s*D\.?\b|\bI\.?\s*D\.?\b",
            re.I,
        ),
        "DVC",
    ),
    (re.compile(r"\bPITCH\b", re.I), "DHG"),
    (re.compile(r"\bHOLE\s*(?:CENTRE|CENTER|REF(?:ERENCE)?)\b", re.I), "DHG"),
    (re.compile(r"\bLOCATION\b", re.I), "DHG"),
    (re.compile(r"\b(?:X|Y)\s*(?:COORD(?:INATE)?S?)\b", re.I), "DHG"),
    (re.compile(r"\bREF\s+(?:DIM(?:ENSION)?|DIM\.?)\b", re.I), "DHG"),
    (re.compile(r"\b(?:HOLE|Holes)\s+(?:CENTRE|CENTER|REF)\b", re.I), "DHG"),
]

_CRITICAL_SPECIAL = re.compile(r"^(?:C|S|I|\*|CRITICAL|SAFETY|IMPORTANT)$", re.I)


def _norm_key(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().upper())


def _is_critical_dimension(
    parameter: str | None,
    specification: str | None,
    special_char: str | None,
) -> bool:
    sc = _norm_key(special_char)
    if sc and _CRITICAL_SPECIAL.match(sc):
        return True
    param = parameter or ""
    if "*" in param:
        return True
    spec = specification or ""
    return "*" in spec


def infer_moi_qti_from_parameter(
    parameter: str | None,
    specification: str | None = None,
    special_char: str | None = None,
) -> str | None:
    """Return QTI code inferred from parameter / row context, or None."""
    if _is_critical_dimension(parameter, specification, special_char):
        return "DHG"

    text = _norm_key(parameter)
    if not text:
        return None

    for pattern, code in _PARAM_PATTERNS:
        if pattern.search(text):
            return code
    return None


def _normalize_raw_moi(raw: str | None) -> str | None:
    """Map a raw MOI string to a QTI code when parameter inference does not apply."""
    s = _norm_key(raw)
    if not s:
        return None

    if s in {"VISUAL", "VISUAL INSPECTION", "VISUVAL"} or "VISUAL" in s:
        return "VIS"

    if "DFT" in s:
        return "DFT"

    if s in {"TPG", "TG", "THREAD PLUG GAUGE", "THREAD PLUG GUAGE", "THREAD GAUGE", "THREAD GUAGE"}:
        return "TPG"
    if "THREAD PLUG" in s or "THREAD GAUGE" in s or "GO AND NO GO THREAD" in s:
        return "TPG"
    if "THREAD RING" in s or ("PLUG GAU" in s and "THREAD" in s):
        return "TPG"

    if s in {"BEVEL", "BP", "B.P", "B.P.", "BEVEL PROTRACTOR", "BEVEL PROTECTOR", "BEVEL PROTRACOR"}:
        return "BP"
    if "BEVEL" in s or "PROTRACTOR" in s or "PROTECTOR" in s:
        return "BP"

    if re.search(r"M\.?\s*TAPE|MEASURING TAPE|MEASURE TAPE", s):
        return "MT"

    if re.match(r"^(MIC|MM|DMM|MICRO\s*METER|MICROMETER|MICRO\s*METRE)$", s.replace(".", "")):
        return "DMM"
    if "MICROMETER" in s or "MICROMET" in s or s.startswith("MIC ") or s == "MIC":
        return "DMM"

    if s == "CMM" or "COORDINATE" in s:
        return "CMM"

    if s in {"DHG", "DHI", "VHG", "V.H.G", "V.H.G.", "DGH"}:
        return "DHG"
    if re.search(r"HEIGHT\s*(GAU|GAGE|GUAGE|GUAGE)|HIEGHT|HIGHT\s*GU", s):
        return "DHG"
    if "VERNIER HEIGHT" in s or "VENIRE HEIGHT" in s or "VENIRE HIGHT" in s:
        return "DHG"
    if s == "HEIGHT GAUGE" or s.startswith("HEIGHT GAUGE"):
        return "DHG"

    if s in {"DVC", "VC", "V.C", "V.C."}:
        return "DVC"
    if re.search(r"VERNIER|VENIRE|VERNNIER|CALLIPER|CALIPER|CALPER|CALIPPER", s):
        if "HEIGHT" in s or "HIGHT" in s or "HIEGHT" in s:
            return "DHG"
        return "DVC"

    if s in {"RG", "R.G", "R.G.", "R.G"}:
        return "RG"
    if "RADIUS" in s and "GAU" in s:
        return "RG"
    if s == "RADIUS GAUGE" or s.startswith("RADIUS GAUG"):
        return "RG"

    if re.search(r"CHECKING\s*GAU|CHECKING\s*WITH\s*GAU|PARALLEL\s*GAU|PITCH\s*GAU", s):
        if "THREAD" in s:
            return "TPG"
        if "RADIUS" in s:
            return "RG"
        return "CG"
    if s == "GAUGE" or s.endswith(" GAUGE"):
        return "CG"

    if "DIAL" in s and "GAU" in s:
        return "DG"

    if "QR" in s and "SCAN" in s:
        return "QRS"

    if "BUFF" in s or "BUFFING" in s:
        return "VIS"

    if re.search(r"\bSCALE\b|\bRULER\b|STEEL\s*RULE", s):
        return "SR"

    if "PROJECTOR" in s or "PROFILE" in s:
        return "PP"

    # Already a short QTI code — pass through uppercased.
    if re.fullmatch(r"[A-Z]{2,4}", s):
        return s

    return None


def normalize_method_of_inspection(
    parameter: str | None,
    specification: str | None = None,
    special_char: str | None = None,
    raw_moi: str | None = None,
) -> str | None:
    """
    Return normalized QTI MOI code for a spec / CCP / coating row.

    Parameter-based inference takes precedence. Falls back to raw MOI normalization.
    When MOI is empty, DFT in special_char is treated as DFT meter.
    """
    inferred = infer_moi_qti_from_parameter(parameter, specification, special_char)
    if inferred:
        return inferred

    moi = _normalize_raw_moi(raw_moi)
    if moi:
        return moi

    sc = _norm_key(special_char)
    if sc and "DFT" in sc:
        return "DFT"

    raw = (raw_moi or "").strip()
    return raw or None


def normalize_ad_row(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize method_of_inspection on one A/B/D-style row dict."""
    moi = normalize_method_of_inspection(
        row.get("parameter"),
        row.get("specification"),
        row.get("special_char"),
        row.get("method_of_inspection"),
    )
    return {**row, "method_of_inspection": moi}


def normalize_bundle_method_of_inspection(bundle: dict[str, Any]) -> dict[str, Any]:
    """Normalize MOI on all spec / CCP / coating rows in a part master bundle."""
    for part in bundle.get("parts") or []:
        for key in ("spec_rows", "ccp_rows", "coating_rows"):
            part[key] = [normalize_ad_row(r) for r in part.get(key) or []]
    return bundle
