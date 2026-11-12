"""TheAIQualisys Cadence™ plan names — same four tiers on every desktop product."""

from __future__ import annotations

from app.licensing.constants import (
    PRODUCT_ASN_AUTO_FILLER,
    PRODUCT_ASN_PDF_PRINTER,
    PRODUCT_QR_CODE,
)

CADENCE_CATALOG_LINE = "Choose your cadence: Pulse → Season → Horizon → Orbit"

# Stable prefixes for plan codes: {PREFIX}_PULSE_1SEAT, …
CADENCE_PRODUCT_PREFIX: dict[str, str] = {
    PRODUCT_QR_CODE: "QR",
    PRODUCT_ASN_PDF_PRINTER: "ASN_PDF",
    PRODUCT_ASN_AUTO_FILLER: "ASN_FILL",
}

# slug, days, display name, customer line, example price INR, sort_order
CADENCE_TIERS: tuple[tuple[str, int, str, str, int, int], ...] = (
    ("PULSE", 30, "Pulse · 1 seat", "Month by month — stay in sync", 499, 10),
    ("SEASON", 90, "Season · 1 seat", "One quarter of uninterrupted use", 1299, 20),
    ("HORIZON", 180, "Horizon · 1 seat", "Six months locked to your machine", 2499, 30),
    ("ORBIT", 365, "Orbit · 1 seat", "Full year around your workflow", 4999, 40),
)


def cadence_product_prefix(product_code: str) -> str:
    code = (product_code or "").strip().upper()
    if code in CADENCE_PRODUCT_PREFIX:
        return CADENCE_PRODUCT_PREFIX[code]
    for suffix in ("_CODE", "_SOFTWARE"):
        if code.endswith(suffix) and len(code) > len(suffix):
            return code[: -len(suffix)].rstrip("_") or code
    return code.replace("-", "_") or "APP"


def cadence_plan_code(product_code: str, tier_slug: str) -> str:
    slug = (tier_slug or "").strip().upper()
    return f"{cadence_product_prefix(product_code)}_{slug}_1SEAT"
