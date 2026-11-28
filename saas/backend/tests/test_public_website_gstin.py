"""Public website shows TheAIQualisys seller GSTIN."""

from pathlib import Path

FRONTEND_SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"


def test_public_website_shows_seller_gstin():
    legal = (FRONTEND_SRC / "companyLegal.ts").read_text(encoding="utf-8")
    landing = (FRONTEND_SRC / "pages" / "LandingPage.tsx").read_text(encoding="utf-8")
    layout = (FRONTEND_SRC / "components" / "Layout.tsx").read_text(encoding="utf-8")
    assert 'SELLER_GSTIN = "29CCTPC6405L1Z4"' in legal
    assert "GSTIN: ${SELLER_GSTIN}" in legal
    assert "SELLER_GSTIN_LABEL" in landing
    assert "SELLER_GSTIN_LABEL" in layout
