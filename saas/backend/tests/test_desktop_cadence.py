from unittest.mock import MagicMock

from app.licensing.cadence import cadence_plan_code, cadence_product_prefix
from app.licensing.constants import PRODUCT_ASN_AUTO_FILLER, PRODUCT_ASN_PDF_PRINTER, PRODUCT_QR_CODE
from app.licensing.models import DesktopPlan, DesktopProduct
from app.licensing.service import _list_products_with_plans


def test_cadence_plan_codes() -> None:
    assert cadence_plan_code(PRODUCT_QR_CODE, "PULSE") == "QR_PULSE_1SEAT"
    assert cadence_plan_code(PRODUCT_QR_CODE, "orbit") == "QR_ORBIT_1SEAT"
    assert cadence_plan_code(PRODUCT_ASN_PDF_PRINTER, "SEASON") == "ASN_PDF_SEASON_1SEAT"
    assert cadence_plan_code(PRODUCT_ASN_AUTO_FILLER, "HORIZON") == "ASN_FILL_HORIZON_1SEAT"


def test_cadence_prefix_future_product() -> None:
    assert cadence_product_prefix("WIDGET_CODE") == "WIDGET"
    assert cadence_plan_code("WIDGET_CODE", "PULSE") == "WIDGET_PULSE_1SEAT"


def test_list_sorts_plans_by_duration() -> None:
    p = DesktopProduct(code="QR_CODE", name="QR", listing_active=1, sort_order=1)
    orbit = DesktopPlan(
        product_id=1, code="QR_ORBIT_1SEAT", name="o", price_inr=1, duration_days=365, listing_active=1, sort_order=40
    )
    pulse = DesktopPlan(
        product_id=1, code="QR_PULSE_1SEAT", name="p", price_inr=1, duration_days=30, listing_active=1, sort_order=10
    )
    orbit.id = 2
    pulse.id = 1
    p.plans = [orbit, pulse]

    class FakeScalars:
        def all(self):
            return [p]

    class FakeResult:
        def scalars(self):
            return FakeScalars()

    db = MagicMock()
    db.execute.return_value = FakeResult()
    rows = _list_products_with_plans(db, include_inactive=True)
    assert [x.code for x in rows[0].plans] == ["QR_PULSE_1SEAT", "QR_ORBIT_1SEAT"]
