"""Customer Profile company / GST billing fields (invoice buyer)."""

from __future__ import annotations

from pathlib import Path

from app.models import Company
from app.routers.auth import _apply_company_billing_profile
from app.schemas import CompanyBillingProfileIn


def test_apply_company_billing_profile_writes_companies_not_seller_settings():
    company = Company(
        company_name="Old Name",
        vendor_code="7200465",
        plan_type="enterprise",
        subscription_status="active",
    )
    body = CompanyBillingProfileIn(
        company_name="Sri Balaji Fabrication Works",
        billing_address="Shop 1",
        billing_city="Bengaluru",
        billing_state="Karnataka",
        billing_state_code="29",
        billing_pincode="560001",
        gstin="29bbbbb0000b1z5",
        phone="9888888888",
    )
    _apply_company_billing_profile(company, body)
    assert company.company_name == "Sri Balaji Fabrication Works"
    assert company.gstin == "29BBBBB0000B1Z5"
    assert company.billing_state_code == "29"
    assert company.billing_city == "Bengaluru"


def test_customer_profile_page_asks_for_company_and_gstin():
    page = (Path(__file__).resolve().parents[2] / "frontend" / "src" / "pages" / "workspace" / "ProfilePage.tsx").read_text(
        encoding="utf-8"
    )
    assert "GSTIN" in page
    assert "Company name" in page
    assert "/auth/company-profile" in page
    assert "Save company details" in page


def test_auth_company_profile_routes_registered():
    src = (Path(__file__).resolve().parents[1] / "app" / "routers" / "auth.py").read_text(encoding="utf-8")
    assert '@router.get("/company-profile"' in src
    assert '@router.put("/company-profile"' in src
