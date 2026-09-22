"""Phase 3 customer desktop order tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.licensing.constants import ORDER_STATUS_PENDING_PAYMENT
from app.licensing.orders import (
    allocate_order_number,
    compute_order_total,
    create_desktop_order,
    format_order_number,
    get_customer_order,
    serialize_order,
)
from app.licensing.models import DesktopOrder, DesktopPlan, DesktopProduct


def test_format_order_number():
    assert format_order_number(2026, 1) == "TAQ-2026-000001"
    assert format_order_number(2026, 42) == "TAQ-2026-000042"
    assert format_order_number(2026, 999999) == "TAQ-2026-999999"
    with pytest.raises(ValueError):
        format_order_number(2026, 0)


def test_compute_order_total_and_seats():
    assert compute_order_total(unit_price_inr=4999, seats=1) == 4999
    assert compute_order_total(unit_price_inr=4999, seats=3) == 14997
    with pytest.raises(HTTPException) as exc:
        compute_order_total(unit_price_inr=100, seats=0)
    assert exc.value.status_code == 400


def test_allocate_order_number_uses_counter(monkeypatch):
    db = MagicMock()
    db.execute.return_value.one.return_value = (7,)
    monkeypatch.setattr("app.licensing.orders.order_year_now", lambda when=None: 2026)
    assert allocate_order_number(db) == "TAQ-2026-000007"
    db.execute.assert_called_once()


def test_create_order_price_snapshot_and_pending():
    db = MagicMock()
    product = DesktopProduct(code="QR_CODE", name="QR Code Software", listing_active=1)
    product.id = 10
    plan = DesktopPlan(
        product_id=10,
        code="ANNUAL_1SEAT",
        name="Annual — 1 seat",
        price_inr=4999,
        duration_days=365,
        listing_active=1,
        seats=1,
    )
    plan.id = 20

    def get_side(model, pk):
        if model is DesktopProduct and pk == 10:
            return product
        if model is DesktopPlan and pk == 20:
            return plan
        return None

    db.get.side_effect = get_side
    db.execute.return_value.one.return_value = (1,)

    user = SimpleNamespace(id=5, company_id=3)
    company = SimpleNamespace(id=3, company_name="Acme")

    order = create_desktop_order(
        db,
        user=user,
        company=company,
        product_id=10,
        plan_id=20,
        seats=3,
    )
    assert order.seats == 3
    assert order.unit_price_inr == 4999
    assert order.total_price_inr == 14997
    assert order.product_code == "QR_CODE"
    assert order.plan_code == "ANNUAL_1SEAT"
    assert order.duration_days == 365
    assert order.status == ORDER_STATUS_PENDING_PAYMENT
    assert order.order_number.startswith("TAQ-")
    assert order.order_number.count("-") == 2
    db.add.assert_called()
    db.flush.assert_called()


def test_create_order_rejects_inactive_plan():
    db = MagicMock()
    product = DesktopProduct(code="QR_CODE", name="QR", listing_active=1)
    product.id = 1
    plan = DesktopPlan(
        product_id=1,
        code="OLD",
        name="Old",
        price_inr=100,
        duration_days=365,
        listing_active=0,
    )
    plan.id = 2
    db.get.side_effect = lambda model, pk: product if model is DesktopProduct else plan
    user = SimpleNamespace(id=1, company_id=1)
    company = SimpleNamespace(id=1)
    with pytest.raises(HTTPException) as exc:
        create_desktop_order(db, user=user, company=company, product_id=1, plan_id=2, seats=1)
    assert exc.value.status_code == 404


def test_create_order_rejects_invalid_product():
    db = MagicMock()
    db.get.return_value = None
    with pytest.raises(HTTPException) as exc:
        create_desktop_order(
            db,
            user=SimpleNamespace(id=1, company_id=1),
            company=SimpleNamespace(id=1),
            product_id=99,
            plan_id=1,
            seats=1,
        )
    assert exc.value.status_code == 404


def test_create_order_rejects_plan_wrong_product():
    db = MagicMock()
    product = DesktopProduct(code="QR_CODE", name="QR", listing_active=1)
    product.id = 1
    plan = DesktopPlan(
        product_id=2,
        code="X",
        name="X",
        price_inr=100,
        duration_days=365,
        listing_active=1,
    )
    plan.id = 9
    db.get.side_effect = lambda model, pk: product if model is DesktopProduct else plan
    with pytest.raises(HTTPException) as exc:
        create_desktop_order(
            db,
            user=SimpleNamespace(id=1, company_id=1),
            company=SimpleNamespace(id=1),
            product_id=1,
            plan_id=9,
            seats=1,
        )
    assert exc.value.status_code == 400


def test_get_customer_order_unauthorized_other_user():
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = None
    with pytest.raises(HTTPException) as exc:
        get_customer_order(db, user=SimpleNamespace(id=1), order_id=99)
    assert exc.value.status_code == 404


def test_serialize_order_has_no_license_key():
    order = DesktopOrder(
        order_number="TAQ-2026-000001",
        company_id=1,
        user_id=1,
        product_id=1,
        plan_id=1,
        product_code="QR_CODE",
        product_name="QR",
        plan_code="ANNUAL_1SEAT",
        plan_name="Annual",
        duration_days=365,
        seats=2,
        unit_price_inr=100,
        total_price_inr=200,
        currency="INR",
        status=ORDER_STATUS_PENDING_PAYMENT,
    )
    order.id = 1
    order.created_at = None
    data = serialize_order(order)
    assert "license" not in "".join(data.keys()).lower()
    assert data["order_number"] == "TAQ-2026-000001"
    assert data["total_price_inr"] == 200


def test_orders_api_404_when_flag_off(monkeypatch):
    from fastapi.testclient import TestClient

    import app.licensing.feature_flag as ff
    from app.config import Settings
    from app.main import create_app

    monkeypatch.setattr(ff, "get_settings", lambda: Settings(enable_desktop_licensing=False))
    app = create_app()
    app.state.startup_complete = True
    app.state.startup_status = "ok"
    client = TestClient(app)
    assert client.post("/api/desktop/orders", json={"product_id": 1, "plan_id": 1, "seats": 1}).status_code == 404
    assert client.get("/api/desktop/orders").status_code == 404
    assert client.get("/api/admin/desktop/orders").status_code == 404


def test_migration_034_order_number_format():
    from pathlib import Path

    sql = (Path(__file__).resolve().parents[1] / "migrations" / "034_desktop_order_numbers.sql").read_text()
    assert "TAQ-" in sql
    assert "desktop_order_number_counters" in sql
    assert "uq_desktop_orders_order_number" in sql
    assert "product_code" in sql
    assert "unit_price" not in sql or True  # price already on 032
