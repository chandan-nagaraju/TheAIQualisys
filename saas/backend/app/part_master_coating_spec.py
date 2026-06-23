"""
Section D — plating / coating thickness specification normalization.

Quality rule: micron thickness acceptance bands must be written as an explicit range
(e.g. ``8 – 12 µm``) or symmetric tolerance (e.g. ``10 ± 2 µm``), not as a lone
``Min 12 micron`` when the process band is 8–12 µm.

All measured values shall be between lower and upper limits (inclusive).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_MICRON_UNIT = r"(?:µm|um|micron|microns|mic)\b"
_MICRON_ANYWHERE = re.compile(rf"\b{_MICRON_UNIT}|µ|\bmic\b", re.I)

_PLATING_PARAM = re.compile(
    r"\b(?:PLATING|COATING|ZINC|CHROME|NICKEL|PHOSPHATE|POWDER)\b.*\bTHICK(?:NESS)?\b|"
    r"\bTHICK(?:NESS)?\b.*\b(?:PLATING|COATING|ZINC|CHROME|NICKEL|PHOSPHATE|POWDER)\b|"
    r"\bPLATING\s*THICK(?:NESS)?\b|"
    r"\bCOATING\s*THICK(?:NESS)?\b|"
    r"\bDFT\b",
    re.I,
)

_RANGE_SPEC = re.compile(
    rf"^\s*([0-9]+(?:\.[0-9]+)?)\s*(?:[-–—]|to)\s*([0-9]+(?:\.[0-9]+)?)\s*(?:{_MICRON_UNIT})?\s*$",
    re.I,
)
_PM_SPEC = re.compile(
    rf"^\s*([0-9]+(?:\.[0-9]+)?)\s*±\s*([0-9]+(?:\.[0-9]+)?)\s*(?:{_MICRON_UNIT})?\s*$",
    re.I,
)
_MIN_ONLY_SPEC = re.compile(
    rf"^\s*(?:min\.?|minimum)\s*([0-9]+(?:\.[0-9]+)?)\s*(?:{_MICRON_UNIT})?\s*$",
    re.I,
)
_MAX_ONLY_SPEC = re.compile(
    rf"^\s*(?:max\.?|maximum)\s*([0-9]+(?:\.[0-9]+)?)\s*(?:{_MICRON_UNIT})?\s*$",
    re.I,
)
_MIN_ONLY_PLATING_LOOSE = re.compile(
    r"^\s*(?:min\.?|minimum|max\.?|maximum)\s*([0-9]+(?:\.[0-9]+)?)\s*$",
    re.I,
)

# When only Min/Max N micron is given for plating thickness, N is treated as the upper
# acceptance limit and the lower limit is N − 4 µm (equivalent to nominal (N−2) ± 2 µm).
_DEFAULT_BAND_WIDTH_UM = 4.0


@dataclass(frozen=True)
class PlatingThicknessRange:
    lower_um: float
    upper_um: float
    nominal_um: float
    tolerance_um: float | None = None

    @property
    def min_um(self) -> float:
        return self.lower_um

    @property
    def max_um(self) -> float:
        return self.upper_um


def _norm_key(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def is_plating_thickness_row(parameter: str | None, specification: str | None = None) -> bool:
    """True for Section D plating/coating thickness rows measured in microns."""
    param = _norm_key(parameter).upper()
    spec = _norm_key(specification)
    if _PLATING_PARAM.search(param):
        return True
    if param and re.search(r"\bDFT\b", param):
        return True
    if spec and _MICRON_ANYWHERE.search(spec):
        if re.search(r"\bTHICK(?:NESS)?\b|\bDFT\b|\bPLATING\b|\bCOATING\b", param, re.I):
            return True
        if re.search(r"\b(?:min|max)\.?\b", spec, re.I) and _MICRON_ANYWHERE.search(spec):
            return True
    return False


def parse_plating_thickness_spec(
    specification: str | None,
    parameter: str | None = None,
) -> PlatingThicknessRange | None:
    """Parse a micron thickness spec into lower/upper limits (µm)."""
    spec = _norm_key(specification)
    if not spec:
        return None
    plating = is_plating_thickness_row(parameter, spec)
    if not plating and not _MICRON_ANYWHERE.search(spec):
        return None

    m = _RANGE_SPEC.match(spec)
    if m:
        lo = float(m.group(1))
        hi = float(m.group(2))
        if lo > hi:
            lo, hi = hi, lo
        nominal = (lo + hi) / 2
        tol = (hi - lo) / 2
        return PlatingThicknessRange(lo, hi, nominal, tol if tol > 0 else None)

    m = _PM_SPEC.match(spec)
    if m:
        nominal = float(m.group(1))
        tol = float(m.group(2))
        return PlatingThicknessRange(nominal - tol, nominal + tol, nominal, tol)

    m = _MIN_ONLY_SPEC.match(spec) or _MAX_ONLY_SPEC.match(spec)
    if m:
        upper = float(m.group(1))
        lower = max(0.0, upper - _DEFAULT_BAND_WIDTH_UM)
        nominal = (lower + upper) / 2
        tol = (upper - lower) / 2
        return PlatingThicknessRange(lower, upper, nominal, tol if tol > 0 else None)

    if plating:
        m = _MIN_ONLY_PLATING_LOOSE.match(spec)
        if m:
            upper = float(m.group(1))
            lower = max(0.0, upper - _DEFAULT_BAND_WIDTH_UM)
            nominal = (lower + upper) / 2
            tol = (upper - lower) / 2
            return PlatingThicknessRange(lower, upper, nominal, tol if tol > 0 else None)

    return None


def format_plating_thickness_spec(
    band: PlatingThicknessRange,
    *,
    prefer_pm: bool = False,
) -> str:
    """Canonical display for a micron thickness acceptance band."""
    lo, hi = band.lower_um, band.upper_um
    if prefer_pm and band.tolerance_um is not None:
        tol = band.tolerance_um
        nominal = band.nominal_um
        lo_pm = nominal - tol
        hi_pm = nominal + tol
        if abs(lo_pm - lo) < 0.05 and abs(hi_pm - hi) < 0.05:
            n_s = f"{nominal:g}"
            t_s = f"{tol:g}"
            return f"{n_s} ± {t_s} µm"
    return f"{lo:g} – {hi:g} µm"


def normalize_plating_thickness_specification(
    parameter: str | None,
    specification: str | None,
) -> str | None:
    """
    Rewrite plating thickness specs to explicit micron bands.

    ``Min 12 micron`` → ``8 – 12 µm`` (when the process band is 8–12 µm).
    ``10 ± 2 µm`` is kept as ± form; ``8 – 12 µm`` is kept as range form.
    """
    raw = _norm_key(specification)
    if not raw:
        return None
    if not is_plating_thickness_row(parameter, raw):
        return raw

    band = parse_plating_thickness_spec(raw, parameter)
    if not band:
        return raw

    prefer_pm = bool(_PM_SPEC.match(raw))
    return format_plating_thickness_spec(band, prefer_pm=prefer_pm)


def normalize_ad_row_coating_spec(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize specification on one Section D row."""
    spec = normalize_plating_thickness_specification(row.get("parameter"), row.get("specification"))
    if spec is None:
        return row
    return {**row, "specification": spec}


def normalize_bundle_part_master_coating_spec(bundle: dict[str, Any]) -> dict[str, Any]:
    """Apply coating spec normalization to all coating rows in a bundle."""
    for part in bundle.get("parts") or []:
        part["coating_rows"] = [normalize_ad_row_coating_spec(r) for r in part.get("coating_rows") or []]
    return bundle
