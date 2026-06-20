"""
Parse multi-sheet Excel workbooks into fir_part_master_bundle_v1 JSON (parts + sections A–D).

Expected sheets (names are matched case-insensitively; aliases allowed):
  • Parts — Part Number, Drawing Rev, Description
  • Section_A (or A, Dimensions, …) — Part Number + A–D style columns for dimensions
  • Section_B (or B, CCP, Complaints, …) — same columns for customer complaint parameters
  • Section_C (or C, Material, …) — Part Number, Material Grade
  • Section_D (or D, Coating, …) — same as A/B for coating rows

Empty section sheets are OK. Part numbers are trimmed; rows without Part Number are skipped.

If no template-style data is found, a **loose FIR layout** fallback runs (single sheet or odd sheet
names): scan the grid for labels like Part No / Description / Draw Rev, and for a table row whose
headers include Parameter + Specification. Tables without a Part Number column are attached to the
part inferred from key–value cells or, when plausible, the sheet name (e.g. B1V24302).
"""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any

import pandas as pd

from app.part_field_validation import sanitize_part_master_alnum_upper

BUNDLE_FORMAT = "fir_part_master_bundle_v1"


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).strip().lower())


def _cell(v: Any) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return str(v).strip()


def _sanitize_part_no(v: Any) -> str:
    """Canonical part number for grouping and bundle output (A–Z, 0–9 only)."""
    return sanitize_part_master_alnum_upper(_cell(v))


_SEPARATOR_TOKENS = {":", "-", "--", "---", ":", "："}


def _is_separator_token(v: str) -> bool:
    return (v or "").strip() in _SEPARATOR_TOKENS


def _is_separator_token(v: str) -> bool:
    t = str(v).strip()
    if not t:
        return True
    return bool(re.fullmatch(r"[:;,\-–—./\\|]+", t))


def _looks_like_section_label(v: str) -> bool:
    n = _norm(v)
    if not n:
        return False
    return n.startswith(
        (
            "a)",
            "b)",
            "c)",
            "d)",
            "section a",
            "section b",
            "section c",
            "section d",
            "a) ",
            "b) ",
            "c) ",
            "d) ",
        )
    )


def _is_material_grade_candidate(v: str) -> bool:
    t = _cell(v)
    if not t or _is_separator_token(t):
        return False
    if _looks_like_section_label(t):
        return False
    n = _norm(t).rstrip(":.- ")
    if n in {
        "material",
        "material grade",
        "c material grade",
        "grade",
        "parameter",
        "specification",
        "method",
    }:
        return False
    # Avoid picking serial numbers like "18" as material grade.
    if re.fullmatch(r"\d+(\.\d+)?", t):
        return False
    return any(ch.isalpha() for ch in t)


def _resolve_sheet(xl: dict[str, pd.DataFrame], aliases: list[str]) -> str | None:
    norm_map = {_norm(k): k for k in xl.keys()}
    for a in aliases:
        n = _norm(a)
        if n in norm_map:
            return norm_map[n]
    return None


def _rename_first_match(df: pd.DataFrame, rules: list[tuple[str, list[str]]]) -> pd.DataFrame:
    """Each rule: (canonical_column_name, header aliases). First matching original column wins."""
    rename: dict[str, str] = {}
    used_orig: set[str] = set()
    for orig in df.columns:
        o = _norm(orig)
        for canon, aliases in rules:
            if orig in used_orig:
                break
            want = {_norm(a) for a in aliases} | {_norm(canon)}
            if o in want:
                rename[str(orig)] = canon
                used_orig.add(orig)
                break
    return df.rename(columns=rename)


_PART_RULES: list[tuple[str, list[str]]] = [
    (
        "part_no",
        [
            "part number",
            "part_no",
            "part no",
            "part",
            "material code",
            "fir part no",
            "part no.",
        ],
    ),
    (
        "drawing_rev",
        [
            "drawing rev",
            "drawing revision",
            "revision",
            "rev",
            "drg rev",
            "rev no",
            "draw. rev no",
            "draw rev no",
            "drawing rev no",
        ],
    ),
    (
        "description",
        ["description", "part name", "name", "material description", "desc"],
    ),
]

_AD_RULES: list[tuple[str, list[str]]] = [
    ("part_no", ["part number", "part_no", "part no", "part"]),
    ("parameter", ["parameter", "param", "sl no", "sl.no", "parameter name", "parameter sl no"]),
    ("specification", ["specification", "spec", "specification (mm)", "spec (mm)"]),
    (
        "special_char",
        [
            "special char",
            "special character",
            "special characteristics",
            "special characteristic",
            "spl char",
            "tolerance",
        ],
    ),
    (
        "method_of_inspection",
        ["method of inspection", "method", "moi", "inspection method"],
    ),
]

_MAT_RULES: list[tuple[str, list[str]]] = [
    ("part_no", ["part number", "part_no", "part no", "part"]),
    ("material_grade", ["material grade", "grade", "material", "mat grade"]),
]


def _ad_rows_from_df(df: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for _, r in df.iterrows():
        param = _cell(r.get("parameter"))
        if not param:
            continue
        rows.append(
            {
                "parameter": param,
                "specification": _cell(r.get("specification")) or None,
                "special_char": _cell(r.get("special_char")) or None,
                "method_of_inspection": _cell(r.get("method_of_inspection")) or None,
            }
        )
    return rows


def _is_serial_only(value: str) -> bool:
    v = (value or "").strip()
    if not v:
        return False
    # 1 / 1.0 / 01 style serials
    return bool(re.fullmatch(r"\d+(?:\.0+)?", v))


def _mat_rows_from_df(df: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for _, r in df.iterrows():
        g = _cell(r.get("material_grade"))
        if g and not _is_serial_only(g):
            rows.append({"material_grade": g})
    return rows


def _guess_part_no_from_sheet_name(name: str, all_sheet_names: list[str]) -> str | None:
    """Use sheet name as part number only when it looks like a part code, not Sheet1 / FIR / etc."""
    raw = str(name).strip()
    if not raw:
        return None
    n = _norm(raw)
    skip = {
        "sheet",
        "sheet1",
        "sheet2",
        "sheet3",
        "fir",
        "report",
        "final inspection report",
        "data",
        "parts",
        "section a",
        "section b",
        "section c",
        "section d",
    }
    if n in skip or n.startswith("sheet "):
        return None
    # Avoid generic first sheet when multiple sheets exist and name is meaningless
    if len(all_sheet_names) > 1 and n in ("sheet1", "sheet 1"):
        return None
    if re.match(r"^[A-Za-z0-9][A-Za-z0-9\-._]{2,50}$", raw) and not raw.lower().startswith("sheet"):
        return sanitize_part_master_alnum_upper(raw.strip())
    return None


def _kv_cell_right(df: pd.DataFrame, r: int, c: int) -> str:
    """Value to the right of a label: next non-empty cell within 4 columns."""
    for dc in (1, 2, 3, 4, 5, 6):
        if c + dc >= df.shape[1]:
            break
        v = _cell(df.iloc[r, c + dc])
        if v and not _is_separator_token(v):
            return v
    return ""


def _value_for_label(df: pd.DataFrame, r: int, c: int) -> str:
    """Label cell at (r,c): value to the right, or below (merged / stacked layouts)."""
    v = _kv_cell_right(df, r, c)
    if v:
        return v
    if r + 1 < len(df):
        below = _cell(df.iloc[r + 1, c])
        if below:
            return below
        if c + 1 < df.shape[1]:
            br = _cell(df.iloc[r + 1, c + 1])
            if br:
                return br
    return ""


def _scan_fir_key_values(df: pd.DataFrame) -> dict[str, str]:
    """Label-in-cell, value-to-the-right scan (header=None DataFrame)."""
    out: dict[str, str] = {}
    max_r = min(100, len(df))
    max_c = min(30, df.shape[1] - 1)
    for r in range(max_r):
        for c in range(max_c):
            raw = df.iloc[r, c]
            if raw is None or (isinstance(raw, float) and pd.isna(raw)):
                continue
            raw_text = str(raw).strip()
            # Inline form: "PART NO : B1V24302", "DRAW.REV NO - #1", etc.
            inline = re.match(
                r"^\s*(part\s*no(?:\.|umber)?|fir\s*part\s*no|draw(?:ing)?\.?\s*rev(?:ision)?\.?\s*no\.?|draw\s*rev\s*no|description|part\s*name|desc)\s*[:\-]\s*(.+?)\s*$",
                raw_text,
                flags=re.IGNORECASE,
            )
            if inline:
                k = _norm(inline.group(1)).rstrip(":.- ")
                v_inline = inline.group(2).strip()
                if v_inline and not _is_separator_token(v_inline):
                    if "part" in k and "no" in k:
                        out.setdefault("part_no", _sanitize_part_no(v_inline))
                    elif "draw" in k or "rev" in k:
                        out.setdefault("drawing_rev", v_inline)
                    elif k in ("description", "part name", "desc"):
                        out.setdefault("description", v_inline)

            lab = _norm(raw_text).rstrip(":.- ")
            if not lab:
                continue
            val = _value_for_label(df, r, c)
            if not val:
                continue
            if re.match(r"^part\s*no(\.|umber)?$", lab) or lab in ("fir part no", "part number"):
                out.setdefault("part_no", _sanitize_part_no(val))
            elif re.match(r"^draw(?:ing)?\.?\s*rev(?:ision)?\.?\s*no\.?$", lab) or lab in (
                "draw rev no",
                "drawing rev",
                "drg rev",
            ):
                out.setdefault("drawing_rev", val)
            elif lab in ("description", "part name", "desc", "material description"):
                out.setdefault("description", val)
    return out


def _row_joined_norm(df: pd.DataFrame, r: int) -> str:
    max_c = min(25, df.shape[1])
    vals = [_norm(_cell(df.iloc[r, c])) for c in range(max_c)]
    return " ".join(x for x in vals if x)


def _find_section_anchor_row(df: pd.DataFrame, section: str) -> int | None:
    """Row index of a loose FIR section title (B/C/D)."""
    max_r = min(220, len(df))
    for r in range(max_r):
        joined = _row_joined_norm(df, r)
        if not joined:
            continue
        if section == "b" and (
            "section b" in joined
            or joined.startswith("b)")
            or ("customer" in joined and "complaint" in joined)
            or "check points" in joined
            or "checkpoints" in joined
        ):
            return r
        if section == "c" and (
            "section c" in joined or ("material" in joined and "grade" in joined)
        ):
            return r
        if section == "d" and ("section d" in joined or "surface coating" in joined):
            return r
    return None


def _is_fir_section_boundary_row(df: pd.DataFrame, r: int) -> bool:
    joined = _row_joined_norm(df, r)
    if not joined:
        return False
    return (
        joined.startswith("b)")
        or joined.startswith("c)")
        or joined.startswith("d)")
        or "section b" in joined
        or "section c" in joined
        or "section d" in joined
        or ("customer" in joined and "complaint" in joined)
        or ("material" in joined and "grade" in joined)
        or "surface coating" in joined
    )


_INSPECTION_METHOD_HINTS = (
    "gauge",
    "gau",
    "caliper",
    "calliper",
    "vernier",
    "micrometer",
    "mic",
    "dft",
    "meter",
    "metre",
    "dhg",
    "dvc",
    "dhi",
    "cmm",
    "tpg",
    "plug",
    "height",
    "visual",
    "go no go",
    "thread",
    "projector",
    "profile",
    "scale",
    "ruler",
)


def _looks_like_inspection_method(v: str) -> bool:
    n = _norm(v)
    if not n:
        return False
    if n in {"visual", "visual inspection", "ok", "n/a", "na"}:
        return True
    return any(h in n for h in _INSPECTION_METHOD_HINTS)


def _looks_like_special_char_tag(v: str) -> bool:
    n = _norm(v)
    if not n:
        return False
    return n in {"c", "s", "i", "critical", "safety", "important", "spl char", "special char"}


def _parse_ad_fields_from_rest(rest: list[str]) -> tuple[str | None, str | None, str | None]:
    """Map trailing cells to specification / special_char / method_of_inspection."""
    if not rest:
        return None, None, None
    if len(rest) == 1:
        if _looks_like_inspection_method(rest[0]):
            return None, None, rest[0]
        return _normalize_spec_value(rest[0]), None, None
    if len(rest) == 2:
        spec = _normalize_spec_value(rest[0])
        if _looks_like_inspection_method(rest[1]):
            return spec, None, rest[1]
        if _looks_like_special_char_tag(rest[1]):
            return spec, rest[1], None
        return spec, None, rest[1]
    spec = _normalize_spec_value(rest[0])
    if _looks_like_inspection_method(rest[1]) and not _looks_like_special_char_tag(rest[1]):
        return spec, None, rest[1]
    if len(rest) >= 3 and _looks_like_inspection_method(rest[2]):
        special = rest[1] if _looks_like_special_char_tag(rest[1]) else None
        return spec, special, rest[2]
    if _looks_like_inspection_method(rest[-1]):
        special = rest[1] if len(rest) > 2 and not _looks_like_inspection_method(rest[1]) else None
        return spec, special, rest[-1]
    return spec, rest[1] if len(rest) > 1 else None, rest[2] if len(rest) > 2 else None


def _is_ad_table_header_row(vals: list[str]) -> bool:
    norms = {_norm(v) for v in vals if v}
    if "parameter" in norms:
        return True
    if "sl no" in norms or "sl.no" in norms:
        if "specification" in norms or any("specification" in x for x in norms):
            return True
    return False


def _ad_row_from_loose_row_vals(vals: list[str]) -> dict[str, Any] | None:
    if _is_ad_table_header_row(vals):
        return None
    non_empty = [v for v in vals if v]
    if not non_empty:
        return None
    idx = 1 if re.fullmatch(r"\d+(?:\.\d+)?", non_empty[0]) else 0
    if idx >= len(non_empty):
        return None
    parameter = non_empty[idx].strip()
    if not parameter or _norm(parameter) in {"parameter", "part", "part no", "part number"}:
        return None
    spec, special, method = _parse_ad_fields_from_rest(non_empty[idx + 1 :])
    return {
        "parameter": parameter,
        "specification": spec,
        "special_char": special,
        "method_of_inspection": method,
    }


def _find_ad_header_row(df: pd.DataFrame, min_row: int = 0) -> int | None:
    for r in range(min_row, min(100, len(df))):
        cells: list[str] = []
        for c in range(min(28, df.shape[1])):
            v = df.iloc[r, c]
            if v is None or (isinstance(v, float) and pd.isna(v)):
                cells.append("")
            else:
                cells.append(_norm(str(v)))
        has_param_col = any(
            bool(x) and (x == "parameter" or (x.startswith("parameter") and "sl" not in x))
            for x in cells
        )
        has_spec = any("specification" in x for x in cells) or any(x in ("spec", "spec(mm)", "spec (mm)") for x in cells)
        if has_param_col and has_spec:
            return r
    return None


def _ad_colmap_from_header_row(df: pd.DataFrame, hdr: int) -> dict[str, int]:
    m: dict[str, int] = {}
    for c in range(df.shape[1]):
        raw = df.iloc[hdr, c]
        if raw is None or (isinstance(raw, float) and pd.isna(raw)):
            continue
        h = _norm(str(raw))
        if not h:
            continue
        if "parameter" in h and "sl" in h:
            continue
        if h == "parameter" or (h.startswith("parameter") and "sl" not in h):
            m.setdefault("parameter", c)
        elif "specification" in h or h in ("spec", "spec(mm)", "spec (mm)"):
            m.setdefault("specification", c)
        elif "special" in h:
            m.setdefault("special_char", c)
        elif "method" in h:
            m.setdefault("method_of_inspection", c)
    return m


def _parse_loose_ad_table(
    df: pd.DataFrame,
    start_row: int = 0,
    end_row: int | None = None,
) -> list[dict[str, Any]]:
    hdr = _find_ad_header_row(df, min_row=start_row)
    if hdr is None:
        return []
    if end_row is not None and hdr >= end_row:
        return []
    cmap = _ad_colmap_from_header_row(df, hdr)
    pc = cmap.get("parameter")
    if pc is None:
        return []
    sc = cmap.get("specification")
    spc = cmap.get("special_char")
    moi = cmap.get("method_of_inspection")
    rows: list[dict[str, Any]] = []
    empty_run = 0
    stop = min(end_row if end_row is not None else len(df), hdr + 250, len(df))
    for r in range(hdr + 1, stop):
        if _is_fir_section_boundary_row(df, r):
            break
        param = _cell(df.iloc[r, pc])
        if not param:
            empty_run += 1
            if empty_run >= 6:
                break
            continue
        empty_run = 0
        if _norm(param) in {"parameter", "part", "part no", "part number"}:
            continue
        spec_v = _cell(df.iloc[r, sc]) if sc is not None else ""
        sch = _cell(df.iloc[r, spc]) if spc is not None else ""
        meth = _cell(df.iloc[r, moi]) if moi is not None else ""
        if sch and not meth and _looks_like_inspection_method(sch):
            meth, sch = sch, ""
        elif not sch and not meth:
            vals = [_cell(df.iloc[r, c]) for c in range(min(25, df.shape[1]))]
            parsed = _ad_row_from_loose_row_vals(vals)
            if parsed and parsed["parameter"] == param:
                spec_v = parsed.get("specification") or spec_v
                sch = parsed.get("special_char") or sch
                meth = parsed.get("method_of_inspection") or meth
        rows.append(
            {
                "parameter": param,
                "specification": spec_v or None,
                "special_char": sch or None,
                "method_of_inspection": meth or None,
            }
        )
    return rows


def _ad_row_from_colmap(df: pd.DataFrame, r: int, cmap: dict[str, int]) -> dict[str, Any] | None:
    """Read one A/B/D-style row using a header column map from Section A."""
    pc = cmap.get("parameter")
    if pc is None:
        return None
    param = _cell(df.iloc[r, pc])
    if not param or _norm(param) in {"parameter", "part", "part no", "part number"}:
        return None
    sc = cmap.get("specification")
    spc = cmap.get("special_char")
    moi = cmap.get("method_of_inspection")
    spec_v = _cell(df.iloc[r, sc]) if sc is not None else ""
    sch = _cell(df.iloc[r, spc]) if spc is not None else ""
    meth = _cell(df.iloc[r, moi]) if moi is not None else ""
    if sch and not meth and _looks_like_inspection_method(sch):
        meth, sch = sch, ""
    if not spec_v and not sch and not meth:
        vals = [_cell(df.iloc[r, c]) for c in range(min(25, df.shape[1]))]
        parsed = _ad_row_from_loose_row_vals(vals)
        if parsed and parsed["parameter"] == param:
            spec_v = parsed.get("specification") or spec_v
            sch = parsed.get("special_char") or sch
            meth = parsed.get("method_of_inspection") or meth
    return {
        "parameter": param,
        "specification": spec_v or None,
        "special_char": sch or None,
        "method_of_inspection": meth or None,
    }


def _is_section_b_boilerplate_row(joined_norm: str) -> bool:
    if not joined_norm:
        return True
    if joined_norm.startswith("b)") or joined_norm.startswith("section b"):
        return True
    if "cpi" in joined_norm and ("issue" in joined_norm or "100" in joined_norm):
        return True
    if "customer" in joined_norm and "complaint" in joined_norm:
        return True
    return False


def _dedupe_ad_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str | None, str | None, str | None]] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        key = (
            row["parameter"],
            row.get("specification"),
            row.get("special_char"),
            row.get("method_of_inspection"),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _scan_section_b_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Parse Section B (CCP) from loose single-sheet FIR layouts."""
    b_anchor = _find_section_anchor_row(df, "b")
    if b_anchor is None:
        return []
    c_anchor = _find_section_anchor_row(df, "c")

    rows = _parse_loose_ad_table(df, start_row=b_anchor, end_row=c_anchor)
    if rows:
        return rows

    # Many FIR templates omit the repeated Parameter/Specification header under Section B.
    hdr = _find_ad_header_row(df, min_row=0)
    cmap = _ad_colmap_from_header_row(df, hdr) if hdr is not None else {}
    stop = c_anchor if c_anchor is not None else len(df)
    out: list[dict[str, Any]] = []
    for r in range(b_anchor + 1, min(stop, len(df))):
        joined = _row_joined_norm(df, r)
        if not joined:
            continue
        if _is_fir_section_boundary_row(df, r):
            break
        if _is_section_b_boilerplate_row(joined):
            continue
        vals = [_cell(df.iloc[r, c]) for c in range(min(25, df.shape[1]))]
        if _is_ad_table_header_row(vals):
            continue
        row: dict[str, Any] | None = None
        if cmap.get("parameter") is not None:
            row = _ad_row_from_colmap(df, r, cmap)
        if row is None:
            row = _ad_row_from_loose_row_vals(vals)
        if row:
            out.append(row)
    return _dedupe_ad_rows(out)


def _scan_material_grade_cells(df: pd.DataFrame) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_grade(v: str) -> None:
        vv = _cell(v)
        if not _is_material_grade_candidate(vv):
            return
        if vv in seen:
            return
        seen.add(vv)
        out.append({"material_grade": vv})

    max_r = min(120, len(df))
    max_c = min(25, df.shape[1] - 1)
    for r in range(max_r):
        for c in range(max_c):
            raw = df.iloc[r, c]
            if raw is None or (isinstance(raw, float) and pd.isna(raw)):
                continue
            lab = _norm(str(raw)).rstrip(":.- ")
            if "material" in lab and "grade" in lab:
                # Prefer textual grade candidates near the label, not serial numbers.
                local_candidates: list[str] = []
                for dc in range(1, min(12, df.shape[1] - c)):
                    v_right = _cell(df.iloc[r, c + dc])
                    if v_right:
                        local_candidates.append(v_right)
                for rr in range(r + 1, min(r + 6, len(df))):
                    for cc in range(0, min(25, df.shape[1])):
                        v_near = _cell(df.iloc[rr, cc])
                        if v_near:
                            local_candidates.append(v_near)
                picked = False
                for cand in local_candidates:
                    if _is_material_grade_candidate(cand):
                        add_grade(cand)
                        picked = True
                        break
                if not picked:
                    add_grade(_value_for_label(df, r, c))

    # Section-C block fallback: after "C) Material Grade", collect textual values until next section.
    for r in range(max_r):
        row_cells = [_cell(df.iloc[r, c]) for c in range(min(25, df.shape[1]))]
        row_text = " ".join(x for x in row_cells if x)
        if "material" not in _norm(row_text) or "grade" not in _norm(row_text):
            continue
        for rr in range(r + 1, min(r + 12, len(df))):
            next_cells = [_cell(df.iloc[rr, cc]) for cc in range(min(25, df.shape[1]))]
            joined = " ".join(x for x in next_cells if x).strip()
            if not joined:
                continue
            if _looks_like_section_label(joined) or _norm(joined).startswith("d "):
                break
            for cand in next_cells:
                if _is_material_grade_candidate(cand):
                    add_grade(cand)
    return out


def _normalize_material_grade(raw: str) -> str | None:
    """
    Normalize material-grade candidates and drop obvious non-grade tokens
    (e.g. serial numbers, row counters, section labels).
    """
    v = (raw or "").strip()
    if not v:
        return None
    n = _norm(v)
    # Skip common non-data tokens from Section C rows
    if n in {
        "sl no",
        "sl.no",
        "s no",
        "parameter",
        "material grade",
        "material",
        "grade",
        "c",
        "section c",
    }:
        return None
    # Pure serial numbers are not material grades
    if re.fullmatch(r"\d+(?:\.\d+)?", v):
        return None
    return v


def _scan_section_c_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    """
    Parse Section C from loose FIR sheets where key/value may be split across cells.
    Handles rows like:
      [sl_no, material_grade] -> [18, "IS 2062 ..."]
      [label, value]          -> ["Material Grade", "BSK46"]
      [single cell value]     -> ["BSK46"]
    """
    out: list[dict[str, Any]] = []
    max_r = min(200, len(df))
    max_c = min(25, df.shape[1])

    # Try anchor-based scan near "Section C" headers first.
    section_c_rows: list[int] = []
    for r in range(max_r):
        row_vals = [_norm(_cell(df.iloc[r, c])) for c in range(max_c)]
        joined = " ".join([x for x in row_vals if x])
        if "section c" in joined or ("material" in joined and "grade" in joined):
            section_c_rows.append(r)

    def add_candidate(raw_val: str) -> None:
        g = _normalize_material_grade(raw_val)
        if g:
            out.append({"material_grade": g})

    def parse_row_values(r: int) -> None:
        vals = [_cell(df.iloc[r, c]) for c in range(max_c)]
        non_empty = [v for v in vals if v]
        if not non_empty:
            return
        # Case: slno in first cell + actual grade in later cell.
        if len(non_empty) >= 2 and re.fullmatch(r"\d+(?:\.\d+)?", non_empty[0]):
            for v in non_empty[1:]:
                add_candidate(v)
            return
        # Case: label + value split.
        if len(non_empty) >= 2 and ("material" in _norm(non_empty[0]) or "grade" in _norm(non_empty[0])):
            for v in non_empty[1:]:
                add_candidate(v)
            return
        # Fallback: any non-empty token in row can be a grade candidate.
        for v in non_empty:
            add_candidate(v)

    # Parse rows after section headers (up to a small window).
    for sr in section_c_rows:
        for r in range(sr + 1, min(sr + 20, max_r)):
            # Stop when another section starts.
            first_cells = " ".join(_norm(_cell(df.iloc[r, c])) for c in range(min(4, max_c)))
            if "section d" in first_cells or "surface coating" in first_cells or "section b" in first_cells:
                break
            parse_row_values(r)

    # Fallback to original label-based scan across whole sheet.
    for row in _scan_material_grade_cells(df):
        add_candidate(str(row.get("material_grade") or ""))

    # Dedupe
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for r in out:
        g = r["material_grade"]
        key = _norm(g)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    return deduped


def _normalize_spec_value(raw: str) -> str | None:
    v = (raw or "").strip()
    if not v:
        return None
    n = _norm(v)
    if n in {"specification", "spec", "parameter", "special char", "method"}:
        return None
    # Reject simple serial numbers accidentally captured as spec
    if re.fullmatch(r"\d+(?:\.\d+)?", v):
        return None
    return v


def _scan_section_d_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    """
    Parse Section D from loose FIR sheets when header mapping fails.
    Supports row forms where parameter/spec/method may be split across cells.
    """
    out: list[dict[str, Any]] = []
    max_r = min(220, len(df))
    max_c = min(25, df.shape[1])

    section_d_rows: list[int] = []
    for r in range(max_r):
        row_vals = [_norm(_cell(df.iloc[r, c])) for c in range(max_c)]
        joined = " ".join([x for x in row_vals if x])
        if "section d" in joined or "surface coating" in joined:
            section_d_rows.append(r)

    def parse_candidate_row(r: int) -> None:
        vals = [_cell(df.iloc[r, c]) for c in range(max_c)]
        joined_norm = " ".join(_norm(v) for v in vals if v)
        if "sampling plan" in joined_norm or "inspector" in joined_norm or "status of inspection" in joined_norm:
            return
        row = _ad_row_from_loose_row_vals(vals)
        if not row:
            return
        out.append(row)

    for sr in section_d_rows:
        for r in range(sr + 1, min(sr + 60, max_r)):
            first_cells = " ".join(_norm(_cell(df.iloc[r, c])) for c in range(min(4, max_c)))
            if "inspector name" in first_cells or "sampling plan" in first_cells:
                break
            parse_candidate_row(r)

    # Dedupe by key tuple
    seen: set[tuple[str, str | None, str | None, str | None]] = set()
    deduped: list[dict[str, Any]] = []
    for row in out:
        key = (
            row["parameter"],
            row.get("specification"),
            row.get("special_char"),
            row.get("method_of_inspection"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _try_parse_loose_fir_workbook(content: bytes, source_filename: str | None = None) -> dict[str, Any] | None:
    """
    Second pass: FIR-style flat sheets (no Parts / Section_* tabs, or wrong header row).
    Returns a full bundle dict or None if nothing usable.
    """
    try:
        xl0 = pd.read_excel(io.BytesIO(content), sheet_name=None, header=None, engine=None)
    except Exception:
        return None
    if not xl0:
        return None
    names = list(xl0.keys())
    # part_no -> {drawing_rev, description, spec_rows, ccp_rows, material_rows, coating_rows}
    buckets: dict[str, dict[str, Any]] = {}

    def ensure(pn: str) -> dict[str, Any]:
        if pn not in buckets:
            buckets[pn] = {
                "drawing_rev": None,
                "description": None,
                "spec_rows": [],
                "ccp_rows": [],
                "material_rows": [],
                "coating_rows": [],
            }
        return buckets[pn]

    global_pn: str | None = None
    for df in xl0.values():
        if df is None or df.empty:
            continue
        kv0 = _scan_fir_key_values(df)
        if kv0.get("part_no"):
            global_pn = _sanitize_part_no(kv0["part_no"])
            break

    filename_pn: str | None = None
    if source_filename:
        stem = Path(source_filename).stem.strip()
        if stem and _guess_part_no_from_sheet_name(stem, [stem]):
            filename_pn = _sanitize_part_no(stem)

    def _split_spec_coating(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        spec: list[dict[str, Any]] = []
        coat: list[dict[str, Any]] = []
        for row in rows:
            p = (row.get("parameter") or "").lower()
            s = (row.get("specification") or "").lower()
            m = (row.get("method_of_inspection") or "").lower()
            if (
                "coat" in p
                or "powder" in p
                or "dft" in p
                or "electro" in p
                or "dft" in m
                or "coat" in m
                or ("thickness" in p and ("µ" in s or "micron" in s or "um" in s))
            ):
                coat.append(row)
            else:
                spec.append(row)
        return spec, coat

    for sname, df in xl0.items():
        if df is None or df.empty:
            continue
        kv = _scan_fir_key_values(df)
        pn_kv = kv.get("part_no")
        pn_sheet = _guess_part_no_from_sheet_name(sname, names)
        b_anchor = _find_section_anchor_row(df, "b")
        c_anchor = _find_section_anchor_row(df, "c")
        a_end = b_anchor if b_anchor is not None else c_anchor
        ad_rows = _parse_loose_ad_table(df, start_row=0, end_row=a_end)
        ccp_rows = _scan_section_b_rows(df)
        mats = _scan_section_c_rows(df)
        d_rows = _scan_section_d_rows(df)

        pn = pn_kv or global_pn or pn_sheet
        if not pn and filename_pn and (ad_rows or ccp_rows or mats or d_rows or kv):
            pn = filename_pn
        if pn:
            pn = _sanitize_part_no(pn)
        if not pn:
            continue
        if not ad_rows and not ccp_rows and not mats and not d_rows and not kv:
            continue

        b = ensure(pn)
        if kv.get("drawing_rev"):
            b["drawing_rev"] = kv["drawing_rev"]
        if kv.get("description"):
            b["description"] = kv["description"]
        spec_part, coat_part = _split_spec_coating(ad_rows)
        if d_rows:
            coat_part.extend(d_rows)
        b["spec_rows"].extend(spec_part)
        b["ccp_rows"].extend(ccp_rows)
        b["coating_rows"].extend(coat_part)
        b["material_rows"].extend(mats)

    if not buckets:
        return None

    def _dedupe_ad(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[tuple[str, str | None, str | None, str | None]] = set()
        out: list[dict[str, Any]] = []
        for row in rows:
            t = (
                row["parameter"],
                row.get("specification"),
                row.get("special_char"),
                row.get("method_of_inspection"),
            )
            if t in seen:
                continue
            seen.add(t)
            out.append(row)
        return out

    def _dedupe_material(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        for row in rows:
            g = row.get("material_grade") or ""
            if not g or g in seen:
                continue
            seen.add(g)
            out.append(row)
        return out

    parts_out: list[dict[str, Any]] = []
    for pn in sorted(buckets.keys()):
        b = buckets[pn]
        parts_out.append(
            {
                "part": {
                    "part_no": pn,
                    "drawing_rev": b.get("drawing_rev"),
                    "description": b.get("description"),
                },
                "spec_rows": _dedupe_ad(b["spec_rows"]),
                "ccp_rows": _dedupe_ad(b["ccp_rows"]),
                "material_rows": _dedupe_material(b["material_rows"]),
                "coating_rows": _dedupe_ad(b.get("coating_rows", [])),
            }
        )

    return {"format": BUNDLE_FORMAT, "parts": parts_out}


def _group_by_part(df: pd.DataFrame, part_col: str, builder):
    """builder(df_part_rows: pd.DataFrame) -> list[dict]"""
    if part_col not in df.columns:
        return {}
    out: dict[str, list[dict[str, Any]]] = {}
    for pn, sub in df.groupby(df[part_col].map(lambda x: _sanitize_part_no(x)), dropna=False):
        if not pn:
            continue
        out[pn] = builder(sub.reset_index(drop=True))
    return out


def parse_parts_excel_to_bundle_dict(
    content: bytes,
    source_filename: str | None = None,
    first_sheet_only: bool = False,
) -> dict[str, Any]:
    """
    Returns a dict suitable for PartMasterBundleBody / JSON export.
    Raises ValueError with a short user-facing message on parse issues.
    """
    try:
        xl_raw = pd.read_excel(io.BytesIO(content), sheet_name=None, engine=None)
    except Exception as e:
        raise ValueError(f"Could not read Excel: {e}") from e

    if not xl_raw:
        raise ValueError("Workbook has no sheets.")

    if first_sheet_only:
        first_name = next(iter(xl_raw.keys()))
        xl = {first_name: xl_raw[first_name]}
    else:
        xl = xl_raw

    parts_name = _resolve_sheet(
        xl,
        ["parts", "part list", "part_master", "master", "part master"],
    )

    meta: dict[str, dict[str, str | None]] = {}
    if parts_name:
        pdf = _rename_first_match(xl[parts_name], _PART_RULES)
        if "part_no" not in pdf.columns:
            raise ValueError(
                f'Sheet "{parts_name}" needs a part column (e.g. Part Number). Found: {list(pdf.columns)}'
            )
        for _, r in pdf.iterrows():
            pn = _sanitize_part_no(r.get("part_no"))
            if not pn:
                continue
            meta[pn] = {
                "drawing_rev": _cell(r.get("drawing_rev")) or None,
                "description": _cell(r.get("description")) or None,
            }

    def load_section(sheet_aliases: list[str], rules: list[tuple[str, list[str]]], group_builder) -> dict[str, Any]:
        sn = _resolve_sheet(xl, sheet_aliases)
        if not sn:
            return {}
        df = _rename_first_match(xl[sn], rules)
        if "part_no" not in df.columns:
            return {}
        return _group_by_part(df, "part_no", group_builder)

    by_a = load_section(
        ["section_a", "a", "dimensions", "dim", "section a", "dimension"],
        _AD_RULES,
        _ad_rows_from_df,
    )
    by_b = load_section(
        ["section_b", "b", "ccp", "complaints", "section b", "complaint"],
        _AD_RULES,
        _ad_rows_from_df,
    )
    by_d = load_section(
        ["section_d", "d", "coating", "coatings", "section d", "surface coating"],
        _AD_RULES,
        _ad_rows_from_df,
    )

    sn_c = _resolve_sheet(xl, ["section_c", "c", "material", "materials", "section c"])
    by_c: dict[str, list[dict[str, Any]]] = {}
    if sn_c:
        cdf = _rename_first_match(xl[sn_c], _MAT_RULES)
        if "part_no" in cdf.columns:
            by_c = _group_by_part(cdf, "part_no", _mat_rows_from_df)

    all_parts: set[str] = set(meta) | set(by_a) | set(by_b) | set(by_c) | set(by_d)
    if not all_parts:
        loose = _try_parse_loose_fir_workbook(content, source_filename=source_filename)
        if loose and loose.get("parts"):
            return loose
        if parts_name and len(xl[parts_name]) > 0:
            pdf = _rename_first_match(xl[parts_name], _PART_RULES)
            if "part_no" not in pdf.columns:
                raise ValueError(
                    "Parts sheet needs a column such as Part Number. "
                    f"Found: {[str(c) for c in xl[parts_name].columns]}"
                )
            if not pdf["part_no"].map(lambda x: bool(_cell(x))).any():
                raise ValueError("Parts sheet has rows but no non-empty Part Number values.")
        # Empty template (headers only) or blank workbook → valid JSON, zero parts.
        return {"format": BUNDLE_FORMAT, "parts": []}

    parts_out: list[dict[str, Any]] = []
    for pn in sorted(all_parts):
        m = meta.get(pn, {})
        parts_out.append(
            {
                "part": {
                    "part_no": pn,
                    "drawing_rev": m.get("drawing_rev"),
                    "description": m.get("description"),
                },
                "spec_rows": by_a.get(pn, []),
                "ccp_rows": by_b.get(pn, []),
                "material_rows": by_c.get(pn, []),
                "coating_rows": by_d.get(pn, []),
            }
        )

    return {"format": BUNDLE_FORMAT, "parts": parts_out}


def build_part_master_template_xlsx() -> bytes:
    """Minimal .xlsx with correct sheet names and header rows (openpyxl)."""
    from openpyxl import Workbook

    wb = Workbook()
    p = wb.active
    p.title = "Parts"
    p.append(["Part Number", "Drawing Rev", "Description"])

    def sheet(title: str, headers: list[str]):
        ws = wb.create_sheet(title)
        ws.append(headers)

    sheet("Section_A", ["Part Number", "Parameter", "Specification", "Special Char", "Method of Inspection"])
    sheet("Section_B", ["Part Number", "Parameter", "Specification", "Special Char", "Method of Inspection"])
    sheet("Section_C", ["Part Number", "Material Grade"])
    sheet("Section_D", ["Part Number", "Parameter", "Specification", "Special Char", "Method of Inspection"])

    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()
