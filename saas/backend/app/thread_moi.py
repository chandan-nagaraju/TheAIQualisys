"""
TPG-only Method of Inspection normalization for metric thread rows.

Standardizes thread inspection MOI on part master import/edit:
  • M6 / M8 / M10 / M12 parameters and M#X# specifications → TPG
  • TG → TPG
  • M6 TG (and M8/M10/M12 variants) → TPG
  • Mis-tagged DVC on thread rows → TPG
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


def _normalize_raw_thread_moi(raw: str | None) -> str | None:
    """Map thread-related raw MOI aliases to TPG; return None when not a thread MOI alias."""
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
    if s == "TG":
        return "TPG"
    return None


def normalize_thread_method_of_inspection(
    parameter: str | None,
    specification: str | None = None,
    special_char: str | None = None,
    raw_moi: str | None = None,
) -> str | None:
    """
    Return TPG for metric thread rows and thread MOI aliases; otherwise leave MOI unchanged.

    Does not alter non-thread MOI values (e.g. DVC, DHG, DFT METER).
    """
    _ = special_char  # reserved for future thread + critical context
    if looks_like_thread_specification(parameter, specification):
        return "TPG"

    tpg = _normalize_raw_thread_moi(raw_moi)
    if tpg:
        return tpg

    raw = (raw_moi or "").strip()
    return raw or None


def normalize_ad_row_thread_moi(row: dict[str, Any]) -> dict[str, Any]:
    """Apply TPG normalization to one A/B/D-style row dict."""
    moi = normalize_thread_method_of_inspection(
        row.get("parameter"),
        row.get("specification"),
        row.get("special_char"),
        row.get("method_of_inspection"),
    )
    return {**row, "method_of_inspection": moi}


def normalize_bundle_thread_moi(bundle: dict[str, Any]) -> dict[str, Any]:
    """Apply TPG normalization to all spec / CCP / coating rows in a part master bundle."""
    for part in bundle.get("parts") or []:
        for key in ("spec_rows", "ccp_rows", "coating_rows"):
            part[key] = [normalize_ad_row_thread_moi(r) for r in part.get(key) or []]
    return bundle
