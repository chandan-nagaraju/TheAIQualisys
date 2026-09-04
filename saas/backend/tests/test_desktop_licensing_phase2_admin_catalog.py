"""Phase 2 admin catalog/pricing service tests (no DB required)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.licensing.models import DesktopPlan, DesktopProduct
from app.licensing.service import (
    create_desktop_plan,
    list_active_products_with_plans,
    list_all_products_with_plans,
    patch_desktop_plan,
    patch_desktop_product,
)


def test_patch_product_toggles_listing():
    db = MagicMock()
    product = DesktopProduct(code="QR_CODE", name="QR", listing_active=1, sort_order=10)
    patch_desktop_product(db, product, {"listing_active": False, "name": "QR Code Software"})
    assert product.listing_active == 0
    assert product.name == "QR Code Software"
    db.add.assert_called()


def test_patch_product_rejects_empty_name():
    db = MagicMock()
    product = DesktopProduct(code="QR_CODE", name="QR", listing_active=1)
    with pytest.raises(HTTPException) as exc:
        patch_desktop_product(db, product, {"name": "  "})
    assert exc.value.status_code == 400


def test_patch_plan_price_and_forces_seats_one():
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = None
    plan = DesktopPlan(
        product_id=1,
        code="ANNUAL_1SEAT",
        name="Annual",
        price_inr=4999,
        duration_days=365,
        seats=99,
        listing_active=1,
    )
    plan.id = 5
    patch_desktop_plan(db, plan, {"price_inr": 5999, "listing_active": True})
    assert plan.price_inr == 5999
    assert plan.seats == 1


def test_create_plan_rejects_duplicate_code():
    db = MagicMock()
    existing = DesktopPlan(product_id=1, code="ANNUAL_1SEAT", name="x", price_inr=1, duration_days=365)
    # get_product_or_404 via db.get
    product = DesktopProduct(code="QR_CODE", name="QR")
    product.id = 1
    db.get.return_value = product
    db.execute.return_value.scalar_one_or_none.return_value = existing
    with pytest.raises(HTTPException) as exc:
        create_desktop_plan(
            db,
            product_id=1,
            code="ANNUAL_1SEAT",
            name="Dup",
            description=None,
            price_inr=100,
        )
    assert exc.value.status_code == 409


def test_create_plan_sets_seats_one():
    db = MagicMock()
    product = DesktopProduct(code="QR_CODE", name="QR")
    product.id = 1
    db.get.return_value = product
    db.execute.return_value.scalar_one_or_none.return_value = None
    plan = create_desktop_plan(
        db,
        product_id=1,
        code="promo",
        name="Promo",
        description="x",
        price_inr=1999,
        duration_days=90,
    )
    assert plan.seats == 1
    assert plan.code == "PROMO"
    assert plan.price_inr == 1999
    db.add.assert_called()


def test_list_active_filters_inactive(monkeypatch):
    active = DesktopProduct(code="A", name="A", listing_active=1, sort_order=1)
    active.id = 1
    active.plans = [
        DesktopPlan(product_id=1, code="P1", name="p", price_inr=1, duration_days=365, listing_active=1, sort_order=1),
        DesktopPlan(product_id=1, code="P2", name="p2", price_inr=1, duration_days=365, listing_active=0, sort_order=2),
    ]
    inactive = DesktopProduct(code="B", name="B", listing_active=0, sort_order=2)
    inactive.id = 2
    inactive.plans = []

    class FakeScalars:
        def all(self):
            return [active, inactive]

    class FakeResult:
        def scalars(self):
            return FakeScalars()

    db = MagicMock()
    # list_all returns both; list_active applies where — we simulate execute return for all path
    # For unit test of filter helper: call _list with include flags via public APIs by mocking execute

    from app.licensing import service as svc

    def fake_list(db, *, include_inactive):
        products = [active, inactive] if include_inactive else [active]
        for p in products:
            plans = list(p.plans or [])
            if not include_inactive:
                plans = [pl for pl in plans if pl.listing_active == 1]
            p.plans = plans
        return products

    monkeypatch.setattr(svc, "_list_products_with_plans", fake_list)
    only_active = list_active_products_with_plans(db)
    assert len(only_active) == 1
    assert len(only_active[0].plans) == 1
    all_rows = list_all_products_with_plans(db)
    assert len(all_rows) == 2


def test_admin_products_404_when_flag_off(monkeypatch):
    from fastapi.testclient import TestClient

    import app.licensing.feature_flag as ff
    from app.config import Settings
    from app.main import create_app

    monkeypatch.setattr(ff, "get_settings", lambda: Settings(enable_desktop_licensing=False))
    app = create_app()
    app.state.startup_complete = True
    app.state.startup_status = "ok"
    client = TestClient(app)
    assert client.get("/api/admin/desktop/products").status_code == 404
    assert client.patch("/api/admin/desktop/products/1", json={"name": "x"}).status_code == 404
    assert client.post("/api/admin/desktop/products/1/plans", json={"code": "X", "name": "X", "price_inr": 1}).status_code == 404
