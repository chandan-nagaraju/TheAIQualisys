"""Invoice Excel mapping: ASN layouts without description, repeated invoice numbers."""

from __future__ import annotations

import io

from openpyxl import Workbook

from app.fir_excel import parse_invoice_excel


def _xlsx(headers: list[str], rows: list[list[object]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_asn_excel_maps_material_asn_qty_invoice_no_and_date():
    content = _xlsx(
        [
            "SA No.",
            "Line Item No.",
            "Schedule Line",
            "Material",
            "Mode of",
            "Transporter Code",
            "ASN Qty",
            "Invoice No",
            "Invoice Date",
            "Plant",
        ],
        [
            ["6010190228", "00010", 2109, "BIV044001", "Road", "UNIFLEX", 25, "TDZ6-27-10643", "15.09.2026", "2002"],
            ["6010190228", "00010", 3549, "BIV36703", "Road", "UNIFLEX", 25, "TDZ6-27-10643", "15.09.2026", "2002"],
            ["6010190228", "00010", 3550, "BIV36703", "Road", "UNIFLEX", 25, "TDZ6-27-10644", "15.09.2026", "2002"],
        ],
    )
    rows, cols = parse_invoice_excel(content, filename="asn.xlsx")
    assert cols == ["Part Number", "Description", "Quantity", "Invoice Number", "Date"]
    assert len(rows) == 3
    assert rows[0]["Part Number"] == "BIV044001"
    assert rows[0]["Quantity"] == "25"
    assert rows[0]["Invoice Number"] == "TDZ6-27-10643"
    assert rows[0]["Date"] == "15.09.2026"
    assert rows[0]["Description"] == ""
    assert rows[1]["Part Number"] == "BIV36703"
    assert rows[1]["Invoice Number"] == "TDZ6-27-10643"
    assert rows[2]["Invoice Number"] == "TDZ6-27-10644"


def test_asn_schedule_line_material_header_uses_material_not_line_number():
    content = _xlsx(
        ["Schedule Line Material", "ASN Qty", "Invoice No", "Invoice Date"],
        [["BIV044001", 50, "TDZ6-27-10647", "15.09.2026"]],
    )
    rows, _ = parse_invoice_excel(content, filename="asn.xlsx")
    assert rows[0]["Part Number"] == "BIV044001"
    assert rows[0]["Quantity"] == "50"
    assert rows[0]["Description"] == ""


def test_wrapped_codl_asn_qty_header_maps_quantity():
    content = _xlsx(
        ["Material Code", "Codl.ASN Qty", "Invoice No", "Invoice Date"],
        [["FAY00300", 50, "TDZ6-27-10647", "15.09.2026"]],
    )
    rows, _ = parse_invoice_excel(content, filename="asn.xlsx")
    assert rows[0]["Part Number"] == "FAY00300"
    assert rows[0]["Quantity"] == "50"
    assert rows[0]["Invoice Number"] == "TDZ6-27-10647"


def test_standard_material_code_advised_qty_layout_still_works():
    content = _xlsx(
        ["Plant", "Material Code", "Material Desc.", "Vendor Code", "Invoice/DC No.", "Advised Qty", "DC Date"],
        [["2002", "BIV044001", "BANJO", "V1", "INV-1", 10, "15.09.2026"]],
    )
    rows, _ = parse_invoice_excel(content, filename="invoice.xlsx")
    assert rows[0]["Part Number"] == "BIV044001"
    assert rows[0]["Description"] == "BANJO"
    assert rows[0]["Quantity"] == "10"
    assert rows[0]["Invoice Number"] == "INV-1"
    assert rows[0]["Date"] == "15.09.2026"
