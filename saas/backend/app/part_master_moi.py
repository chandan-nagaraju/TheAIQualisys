"""
Part master Method of Inspection normalization on import/edit.

Scope (parameter → QTI only):
  • Metric thread (M6/M8/M10/M12, M#X#) → TPG
  • Thickness → DMM
  • Radius → RG
  • Angle → BP
  • Dia, Width, OD, ID → DVC

Thread MOI aliases (TG, M6 TG, …) → TPG. All other MOI values are unchanged.
"""

from __future__ import annotations

import re
from typing import Any

_THREAD_SIZE = re.compile(r"\bM(?:6|8|10|12)\b", re.I)
_THREAD_DESIGNATION = re.compile(r"\bM\d+(?:\.\d+)?\s*[X×]\d+(?:\.\d+)?\b", re.I)
_THREAD_DESIGNATION_COMPACT = re.compile(r"^M\d+(?:\.\d+)?[X×]\d+(?:\.\d+)?$", re.I)
_THREAD_MOI = re.compile(
    r"^(?:M(?:6|8|10|12)\s*)?(?:TG|TPG|THREAD(?:\s*(?:PLUG)?\s*GAU(?:GE)?)?)$",
    re.I,
)

_PARAM_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bTHICKNESS\b|\bTHK\b|\bTHICK\b", re.I), "DMM"),
    (re.compile(r"\bRADIUS\b|\bRAD\b", re.I), "RG"),
    (re.compile(r"\bANGLE\b|\bBEVEL\b", re.I), "BP"),
    (
        re.compile(
            r"\bDIA\b|\bDIAM\b|\bDIAMETER\b|\bWIDTH\b|\bOD\b|\bID\b|\bO\.?\s*D\.?\b|\bI\.?\s*D\.?\b",
            re.I,
        ),
        "DVC",
    ),
]


def _norm_key(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().upper())


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


def infer_moi_from_parameter(parameter: str | None) -> str | None:
    """Return QTI code inferred from parameter name, or None."""
    text = _norm_key(parameter)
    if not text:
        return None
    for pattern, code in _PARAM_PATTERNS:
        if pattern.search(text):
            return code
    return None


def _normalize_raw_thread_moi(raw: str | None) -> str | None:
    """Map thread-related raw MOI aliases to TPG."""
    s = _norm_key(raw)
    if not s:
        return None
    if _THREAD_MOI.match(s):
        return "TPG"
    if s in {
        "TPG",
        "TG",
        "THREAD PLUG GAUGE",
        "THREAD PLUG GUAGE",
        "THREAD GAUGE",
        "THREAD GUAGE",
    }:
        return "TPG"
    if "THREAD PLUG" in s or "THREAD GAUGE" in s or "GO AND NO GO THREAD" in s:
        return "TPG"
    if "THREAD RING" in s or ("PLUG GAU" in s and "THREAD" in s):
        return "TPG"
    return None


def normalize_part_master_moi(
    parameter: str | None,
    specification: str | None = None,
    special_char: str | None = None,
    raw_moi: str | None = None,
) -> str | None:
    """Normalize MOI for a spec / CCP / coating row (scoped rules only)."""
    _ = special_char

    if looks_like_thread_specification(parameter, specification):
        return "TPG"

    inferred = infer_moi_from_parameter(parameter)
    if inferred:
        return inferred

    tpg = _normalize_raw_thread_moi(raw_moi)
    if tpg:
        return tpg

    raw = (raw_moi or "").strip()
    return raw or None


normalize_thread_method_of_inspection = normalize_part_master_moi


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
