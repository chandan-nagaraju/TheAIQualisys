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

BUNDLE_FORMAT = "fir_part_master_bundle_v1"


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).strip().lower())


def _cell(v: Any) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return str(v).strip()


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


def _mat_rows_from_df(df: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for _, r in df.iterrows():
        g = _cell(r.get("material_grade"))
        if g:
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
        return raw.strip()
    return None


def _kv_cell_right(df: pd.DataFrame, r: int, c: int) -> str:
    """Value to the right of a label: next non-empty cell within 4 columns."""
    for dc in (1, 2, 3, 4):
        if c + dc >= df.shape[1]:
            break
        v = _cell(df.iloc[r, c + dc])
        if v:
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
            lab = _norm(str(raw)).rstrip(":.- ")
            if not lab:
                continue
            val = _value_for_label(df, r, c)
            if not val:
                continue
            if re.match(r"^part\s*no(\.|umber)?$", lab) or lab in ("fir part no", "part number"):
                out.setdefault("part_no", val)
            elif re.match(r"^draw(?:ing)?\.?\s*rev(?:ision)?\.?\s*no\.?$", lab) or lab in (
                "draw rev no",
                "drawing rev",
                "drg rev",
            ):
                out.setdefault("drawing_rev", val)
            elif lab in ("description", "part name", "desc", "material description"):
                out.setdefault("description", val)
    return out


def _find_ad_header_row(df: pd.DataFrame) -> int | None:
    for r in range(min(100, len(df))):
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


def _parse_loose_ad_table(df: pd.DataFrame) -> list[dict[str, Any]]:
    hdr = _find_ad_header_row(df)
    if hdr is None:
        return []
    cmap = _ad_colmap_from_header_row(df, hdr)
    pc = cmap.get("parameter")
    if pc is None:
        return []
    sc = cmap.get("specification")
    rows: list[dict[str, Any]] = []
    empty_run = 0
    for r in range(hdr + 1, min(hdr + 250, len(df))):
        param = _cell(df.iloc[r, pc])
        if not param:
            empty_run += 1
            if empty_run >= 6:
                break
            continue
        empty_run = 0
        spec_v = _cell(df.iloc[r, sc]) if sc is not None else ""
        spc = cmap.get("special_char")
        moi = cmap.get("method_of_inspection")
        sch = _cell(df.iloc[r, spc]) if spc is not None else ""
        meth = _cell(df.iloc[r, moi]) if moi is not None else ""
        rows.append(
            {
                "parameter": param,
                "specification": spec_v or None,
                "special_char": sch or None,
                "method_of_inspection": meth or None,
            }
        )
    return rows


def _scan_material_grade_cells(df: pd.DataFrame) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    max_r = min(120, len(df))
    max_c = min(25, df.shape[1] - 1)
    for r in range(max_r):
        for c in range(max_c):
            raw = df.iloc[r, c]
            if raw is None or (isinstance(raw, float) and pd.isna(raw)):
                continue
            lab = _norm(str(raw)).rstrip(":.- ")
            if "material" in lab and "grade" in lab:
                v = _value_for_label(df, r, c)
                if v:
                    out.append({"material_grade": v})
    return out


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
    # part_no -> {drawing_rev, description, spec_rows, material_rows, coating_rows}
    buckets: dict[str, dict[str, Any]] = {}

    def ensure(pn: str) -> dict[str, Any]:
        if pn not in buckets:
            buckets[pn] = {
                "drawing_rev": None,
                "description": None,
                "spec_rows": [],
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
            global_pn = kv0["part_no"]
            break

    filename_pn: str | None = None
    if source_filename:
        stem = Path(source_filename).stem.strip()
        if stem and _guess_part_no_from_sheet_name(stem, [stem]):
            filename_pn = stem

    def _split_spec_coating(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        spec: list[dict[str, Any]] = []
        coat: list[dict[str, Any]] = []
        for row in rows:
            p = (row.get("parameter") or "").lower()
            s = (row.get("specification") or "").lower()
            if (
                "coat" in p
                or "powder" in p
                or "dft" in p
                or "electro" in p
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
        ad_rows = _parse_loose_ad_table(df)
        mats = _scan_material_grade_cells(df)

        pn = pn_kv or global_pn or pn_sheet
        if not pn and filename_pn and (ad_rows or mats or kv):
            pn = filename_pn
        if not pn:
            continue
        if not ad_rows and not mats and not kv:
            continue

        b = ensure(pn)
        if kv.get("drawing_rev"):
            b["drawing_rev"] = kv["drawing_rev"]
        if kv.get("description"):
            b["description"] = kv["description"]
        spec_part, coat_part = _split_spec_coating(ad_rows)
        b["spec_rows"].extend(spec_part)
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
                "ccp_rows": [],
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
    for pn, sub in df.groupby(df[part_col].map(lambda x: _cell(x)), dropna=False):
        if not pn:
            continue
        out[pn] = builder(sub.reset_index(drop=True))
    return out


def parse_parts_excel_to_bundle_dict(content: bytes, source_filename: str | None = None) -> dict[str, Any]:
    """
    Returns a dict suitable for PartMasterBundleBody / JSON export.
    Raises ValueError with a short user-facing message on parse issues.
    """
    try:
        xl = pd.read_excel(io.BytesIO(content), sheet_name=None, engine=None)
    except Exception as e:
        raise ValueError(f"Could not read Excel: {e}") from e

    if not xl:
        raise ValueError("Workbook has no sheets.")

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
            pn = _cell(r.get("part_no"))
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
