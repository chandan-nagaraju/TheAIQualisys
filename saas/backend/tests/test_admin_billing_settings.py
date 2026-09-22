"""Admin Billing Settings — TheAIQualisys seller singleton."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from app.billing_invoices import get_billing_settings, serialize_billing_settings, update_billing_settings
from app.models import BillingSettings


def test_admin_billing_settings_routes_include_optional_trailing_slash():
    src = (Path(__file__).resolve().parents[1] / "app" / "routers" / "admin.py").read_text(encoding="utf-8")
    assert '@router.get("/billing/settings"' in src
    assert '@router.get("/billing/settings/"' in src
    assert '@router.put("/billing/settings"' in src
    assert '@router.put("/billing/settings/"' in src


def test_get_billing_settings_creates_singleton_id_1():
    created: list[BillingSettings] = []
    db = MagicMock()
    db.get.return_value = None

    def _add(row):
        created.append(row)

    db.add.side_effect = _add
    row = get_billing_settings(db)
    assert row.id == 1
    assert created == [row]
    db.flush.assert_called()


def test_update_billing_settings_upserts_same_id():
    existing = BillingSettings(
        id=1,
        invoice_prefix="INV-",
        cgst_rate=9,
        sgst_rate=9,
        igst_rate=18,
    )
    db = MagicMock()
    db.get.return_value = existing
    out = update_billing_settings(
        db,
        {
            "business_name": "TheAIQualisys",
            "address_line1": "Line 1",
            "city": "Bengaluru",
            "state": "Karnataka",
            "state_code": "29",
            "pincode": "560001",
            "country": "India",
            "email": "billing@theaiqualisys.com",
            "phone": "9999999999",
            "gstin": "29AAAAA0000A1Z5",
        },
    )
    assert out is existing
    assert out.id == 1
    assert out.business_name == "TheAIQualisys"
    assert out.city == "Bengaluru"
    assert out.state_code == "29"
    assert "Line 1" in (out.business_address or "")
    payload = serialize_billing_settings(out)
    assert payload["business_name"] == "TheAIQualisys"
    assert payload["city"] == "Bengaluru"
    assert payload["invoice_prefix"] == "INV-"
    assert payload["cgst_rate"] == 9


def test_settings_page_does_not_expose_invoice_prefix_or_gst_rates():
    page = (Path(__file__).resolve().parents[2] / "frontend" / "src" / "pages" / "AdminBillingSettingsPage.tsx").read_text(
        encoding="utf-8"
    )
    assert "Invoice prefix" not in page
    assert "CGST" not in page
    assert "SGST" not in page
    assert "IGST" not in page
    assert "Currency" not in page
    assert 'apiFetch<Settings>("/admin/billing/settings"' in page or 'SETTINGS_PATH = "/admin/billing/settings"' in page
    assert "Save Billing Settings" in page
