"""Excel invoice parsing — same column mapping as legacy Flask app.py upload route."""

from __future__ import annotations

import io
import re
from typing import Any

import pandas as pd

from app.part_field_validation import sanitize_part_master_alnum_upper

def _norm_header(s: Any) -> str:
    text = str(s or "").strip().lower()
    # Excel sometimes uses Unicode slashes in headers.
    text = text.replace("⁄", "/").replace("／", "/").replace("∕", "/")
    # Normalize punctuation and separators so variants like
    # "Invoice/DC No.", "Invoice DC No", "invoice-dc no" all match.
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


COLUMN_MAPPING = {
    "part number": "Part Number",
    "part no": "Part Number",
    "part no ": "Part Number",
    "part_no": "Part Number",
    "part": "Part Number",
    "material code": "Part Number",
    "materialcode": "Part Number",
    "description": "Description",
    "material desc": "Description",
    "material description": "Description",
    "qty": "Quantity",
    "quantity": "Quantity",
    "advised qty": "Quantity",
    "advised quantity": "Quantity",
    # "Advised Qty/Qty" (slash or Unicode slash) → advised qty qty after _norm_header
    "advised qty qty": "Quantity",
    "advised quantity quantity": "Quantity",
    "bill qty": "Quantity",
    "order qty": "Quantity",
    "po qty": "Quantity",
    "ship qty": "Quantity",
    "invoice qty": "Quantity",
    "actual qty": "Quantity",
    "rec qty": "Quantity",
    "received qty": "Quantity",
    "total qty": "Quantity",
    "invoice no": "Invoice Number",
    "invoice number": "Invoice Number",
    "invoice": "Invoice Number",
    "invoice dc no": "Invoice Number",
    "invoice dc number": "Invoice Number",
    "dc no": "Invoice Number",
    "dc number": "Invoice Number",
    "date": "Date",
    "dc date": "Date",
    "document date": "Date",
}

DISPLAY_COLS = [
    "Part Number",
    "Description",
    "Quantity",
    "Invoice Number",
    "Date",
]

# If Quantity matched no column, map headers that clearly mean qty.
_QTY_HEADER_FALLBACK_RE = re.compile(
    r"^("
    r"advised\s+qty(\s+qty)*"
    r"|advised\s+quantity(\s+quantity)*"
    r"|advised\s+.+\b(qty|quantity)\b"
    r"|qty(\s+qty)+"
    r"|quantity(\s+quantity)+"
    r"|bill\s+qty|order\s+qty|ship\s+qty|invoice\s+qty|po\s+qty"
    r"|received\s+qty|rec\s+qty|actual\s+qty|total\s+qty"
    r")$"
)


def _add_fallback_quantity_columns(df: Any, matched_sources: dict[str, list[Any]]) -> None:
    if matched_sources["Quantity"]:
        return
    for col in df.columns:
        key = _norm_header(col)
        if not key:
            continue
        # Never treat a pure location column as quantity.
        if re.search(r"\bcity\b", key) and not re.search(r"\b(qty|quantity)\b", key):
            continue
        if _QTY_HEADER_FALLBACK_RE.match(key):
            matched_sources["Quantity"].append(col)


def _map_mislabeled_advised_city_as_quantity(df: Any, matched_sources: dict[str, list[Any]]) -> None:
    """
    Some vendor exports label quantity as 'Advised City' (numeric values under a wrong header).
    Only applies when no column mapped to Quantity yet, so real Qty / Advised Qty columns win.
    """
    if matched_sources["Quantity"]:
        return
    for col in df.columns:
        if _norm_header(col) == "advised city":
            matched_sources["Quantity"].append(col)
            return
_OLE2_MAGIC = bytes.fromhex("d0cf11e0a1b11ae1")


def _local_tag(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _looks_like_excel2003_xml(content: bytes) -> bool:
    """Excel 2003 XML Spreadsheet is often saved with a .xls extension; content starts with <?xml (not binary BIFF)."""
    s = content.lstrip()
    if s.startswith(bytes([0xEF, 0xBB, 0xBF])):
        s = s[3:]
    return s.startswith(b"<?xml")


def _decode_spreadsheetml(content: bytes) -> str:
    if content.startswith(bytes([0xFF, 0xFE])) or content.startswith(bytes([0xFE, 0xFF])):
        return content.decode("utf-16")
    s = content
    if s.startswith(bytes([0xEF, 0xBB, 0xBF])):
        s = s[3:]
    return s.decode("utf-8", errors="replace")


def _cell_text(cell: Any) -> str:
    val = ""
    for child in cell:
        if _local_tag(child.tag) == "Data":
            val = (child.text or "").strip()
            break
    return val


def _parse_spreadsheetml_table(table: Any) -> list[list[str]]:
    """One <Table> → grid of string rows (handles ss:Index column skips)."""
    grid: list[list[str]] = []
    for row in table:
        if _local_tag(row.tag) != "Row":
            continue
        cells: list[str] = []
        col_idx = 0
        for cell in row:
            if _local_tag(cell.tag) != "Cell":
                continue
            idx_attr = None
            for ak, av in cell.attrib.items():
                if ak.endswith("Index") or _local_tag(ak) == "Index":
                    try:
                        idx_attr = int(av)
                    except ValueError:
                        idx_attr = None
                    break
            if idx_attr is not None:
                while len(cells) < idx_attr - 1:
                    cells.append("")
                col_idx = idx_attr - 1
            while len(cells) <= col_idx:
                cells.append("")
            cells[col_idx] = _cell_text(cell)
            col_idx += 1
        if any(c.strip() for c in cells):
            grid.append(cells)
    return grid


def _read_excel2003_xml_as_dataframe(content: bytes) -> Any:
    import xml.etree.ElementTree as ET

    xml_text = _decode_spreadsheetml(content)
    root = ET.fromstring(xml_text)
    tables: list[Any] = [el for el in root.iter() if _local_tag(el.tag) == "Table"]
    if not tables:
        raise ValueError("Excel XML has no Table element (not a 2003 XML Spreadsheet?)")

    grid: list[list[str]] = []
    for table in tables:
        grid = _parse_spreadsheetml_table(table)
        if grid:
            break
    if not grid:
        return pd.DataFrame()
    max_len = max(len(r) for r in grid)
    for r in grid:
        while len(r) < max_len:
            r.append("")
    header = [str(h).strip() for h in grid[0]]
    body = grid[1:]
    return pd.DataFrame(body, columns=header)


def _invoice_excel_engine(content: bytes, filename: str | None) -> str:
    """
    Pick pandas engine without relying on filename alone (some clients omit or alter it).
    .xlsx is ZIP (PK); legacy .xls is OLE2.
    """
    if len(content) >= 2 and content[:2] == b"PK":
        return "openpyxl"
    if len(content) >= len(_OLE2_MAGIC) and content[: len(_OLE2_MAGIC)] == _OLE2_MAGIC:
        return "xlrd"
    fn = (filename or "").lower()
    if fn.endswith(".xls") and not fn.endswith(".xlsx"):
        return "xlrd"
    return "openpyxl"


def _looks_like_html_xls(content: bytes) -> bool:
    head = content.lstrip()[:256].lower()
    return head.startswith(b"<!") or head.startswith(b"<html") or head.startswith(b"<head") or head.startswith(b"<meta")


def parse_invoice_excel(content: bytes, *, filename: str | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    """Read .xlsx (openpyxl), binary .xls (xlrd), or Excel 2003 XML Spreadsheet (often mislabeled .xls)."""
    fn = (filename or "").lower()

    if _looks_like_excel2003_xml(content):
        df = _read_excel2003_xml_as_dataframe(content)
    else:
        primary = _invoice_excel_engine(content, filename)

        def try_xlrd() -> Any:
            return pd.read_excel(io.BytesIO(content), engine="xlrd")

        def try_openpyxl() -> Any:
            return pd.read_excel(io.BytesIO(content), engine="openpyxl")

        if primary == "xlrd":
            try:
                df = try_xlrd()
            except Exception as e:
                if _looks_like_html_xls(content):
                    raise ValueError(
                        "This file is not a real Excel workbook (it looks like HTML). "
                        "Open it in Microsoft Excel and use Save As → Excel 97–2003 Worksheet (.xls) or .xlsx."
                    ) from e
                raise ValueError(
                    "Could not read this .xls file as Excel. Open it in Excel and save again as .xls or .xlsx, "
                    f"or confirm the server has the 'xlrd' package installed. Detail: {e}"
                ) from e
        else:
            try:
                df = try_openpyxl()
            except Exception as e:
                if (fn.endswith(".xls") and not fn.endswith(".xlsx")) or (
                    len(content) >= len(_OLE2_MAGIC) and content[: len(_OLE2_MAGIC)] == _OLE2_MAGIC
                ):
                    try:
                        df = try_xlrd()
                    except Exception as e2:
                        if _looks_like_html_xls(content):
                            raise ValueError(
                                "This file is not a real Excel workbook (it looks like HTML). "
                                "Save from Excel as .xls or .xlsx, not as Web Page."
                            ) from e2
                        raise ValueError(
                            "Could not read this Excel file as .xlsx or .xls. "
                            f"xlsx: {e}; xls: {e2}"
                        ) from e2
                else:
                    raise
    # Build target columns explicitly so multiple source columns can map to the
    # same canonical field without creating duplicate labels.
    matched_sources: dict[str, list[Any]] = {k: [] for k in DISPLAY_COLS}
    for col in df.columns:
        key = _norm_header(col)
        canon = COLUMN_MAPPING.get(key)
        if canon:
            matched_sources[canon].append(col)

    _add_fallback_quantity_columns(df, matched_sources)
    _map_mislabeled_advised_city_as_quantity(df, matched_sources)

    extracted = pd.DataFrame(index=df.index)
    for canon in DISPLAY_COLS:
        src_cols = matched_sources.get(canon, [])
        if not src_cols:
            extracted[canon] = ""
            continue
        if len(src_cols) == 1:
            extracted[canon] = df[src_cols[0]].fillna("")
            continue
        # If multiple source columns map to the same canonical column (e.g. Date + DC Date),
        # keep the first non-empty value per row.
        sub = df[src_cols].fillna("")
        extracted[canon] = sub.apply(
            lambda row: next((str(v).strip() for v in row if str(v).strip()), ""),
            axis=1,
        )

    for col in DISPLAY_COLS:
        extracted[col] = extracted[col].map(lambda v: "" if v is None else str(v).strip())
    # Keep only rows that contain at least one of the required output values.
    extracted = extracted[
        extracted.apply(lambda r: any(str(v).strip() for v in r.values), axis=1)
    ]
    # Business rule: Part Number can repeat, Invoice Number must be unique.
    # Ignore blank invoice numbers here; required-field validation happens in UI/workflow.
    invoice_series = extracted["Invoice Number"].map(lambda v: str(v).strip())
    seen: set[str] = set()
    dupes: list[str] = []
    for inv in invoice_series:
        if not inv:
            continue
        if inv in seen and inv not in dupes:
            dupes.append(inv)
        seen.add(inv)
    if dupes:
        dupes_str = ", ".join(dupes[:5])
        extra = f" (+{len(dupes) - 5} more)" if len(dupes) > 5 else ""
        raise ValueError(
            "Invoice Number must be unique. Duplicate invoice number(s): "
            f"{dupes_str}{extra}"
        )
    rows = extracted.to_dict(orient="records")
    for row in rows:
        pn = row.get("Part Number")
        if pn is not None:
            row["Part Number"] = sanitize_part_master_alnum_upper(str(pn))
    return rows, DISPLAY_COLS


def sample_size_for_quantity(qty_val: float) -> int | str:
    if qty_val <= 0:
        return ""
    if qty_val <= 1:
        return 1
    if qty_val <= 2:
        return 2
    if qty_val <= 3:
        return 3
    if qty_val <= 4:
        return 4
    return 5


def enrich_rows_with_parts(
    rows: list[dict],
    *,
    parts_by_no: dict[str, tuple[str | None, int | None]] | None = None,
    part_rows: list[tuple[str, str | None, int, int]] | None = None,
    workspace_customer_id: int | None = None,
    param_count_by_part_id: dict[int, int] | None = None,
    default_num_params: int = 17,
) -> list[dict]:
    """Resolve part master row per invoice line using customer-scoped parts when ``part_rows`` is set."""
    from collections import defaultdict

    param_count_by_part_id = param_count_by_part_id or {}
    by_pn: dict[str, list[tuple[str | None, int, int]]] = defaultdict(list)
    if part_rows is not None:
        for pno, dr, pid, cid in part_rows:
            by_pn[str(pno).strip()].append((dr, pid, cid))
    elif parts_by_no is not None:
        for pno, (dr, pid) in parts_by_no.items():
            by_pn[str(pno).strip()].append((dr, pid if pid is not None else -1, -1))
    out = []
    for r in rows:
        row = dict(r)
        part_no = str(row.get("Part Number", "")).strip()
        draw_rev: str | None = None
        part_id: int | None = None
        cands = by_pn.get(part_no, [])
        if not cands:
            pass
        elif len(cands) == 1:
            dr, pid, _cid = cands[0]
            draw_rev = dr
            part_id = None if pid == -1 else pid
        elif workspace_customer_id is not None:
            for dr, pid, cid in cands:
                if cid == workspace_customer_id:
                    draw_rev, part_id = dr, pid
                    break
        try:
            qty_val = float(row.get("Quantity") or 0)
        except (TypeError, ValueError):
            qty_val = 0
        row["draw_rev"] = draw_rev or ""
        row["sample_size"] = sample_size_for_quantity(qty_val)
        if part_id is not None and part_id > 0:
            row["num_params"] = param_count_by_part_id.get(part_id, default_num_params)
        else:
            row["num_params"] = default_num_params
        out.append(row)
    return out
