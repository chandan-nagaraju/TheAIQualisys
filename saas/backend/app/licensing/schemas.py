"""Pydantic schemas for desktop licensing (Phase 1–2)."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class DesktopPlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    code: str
    name: str
    description: Optional[str] = None
    price_inr: int
    duration_days: int
    seats: int
    listing_active: bool
    sort_order: int


class DesktopProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    description: Optional[str] = None
    listing_active: bool
    trial_enabled: bool
    trial_duration_days: int
    sort_order: int
    buy_url_path: Optional[str] = None


class DesktopProductWithPlansOut(DesktopProductOut):
    plans: List[DesktopPlanOut] = Field(default_factory=list)


class DesktopProductPatch(BaseModel):
    """Admin partial update for desktop product catalog fields."""

    name: Optional[str] = None
    description: Optional[str] = None
    listing_active: Optional[bool] = None
    sort_order: Optional[int] = None
    buy_url_path: Optional[str] = None


class DesktopPlanCreate(BaseModel):
    """Create a 1-seat plan (seats always forced to 1 server-side)."""

    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    price_inr: int = Field(ge=0)
    duration_days: int = Field(default=365, ge=1)
    listing_active: bool = True
    sort_order: int = 10


class DesktopPlanPatch(BaseModel):
    code: Optional[str] = Field(default=None, min_length=1, max_length=64)
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    price_inr: Optional[int] = Field(default=None, ge=0)
    duration_days: Optional[int] = Field(default=None, ge=1)
    listing_active: Optional[bool] = None
    sort_order: Optional[int] = None


class LicensingHealthOut(BaseModel):
    enabled: bool
    products_seeded: int
    plans_seeded: int
    phase: str = "3-customer-orders"
    message: str


class DesktopOrderCreate(BaseModel):
    product_id: int = Field(ge=1)
    plan_id: int = Field(ge=1)
    seats: int = Field(ge=1, le=500)


class DesktopOrderOut(BaseModel):
    id: int
    order_number: str
    company_id: int
    user_id: int
    product_id: int
    plan_id: int
    product_code: str
    product_name: str
    plan_code: str
    plan_name: str
    duration_days: int
    seats: int
    unit_price_inr: int
    total_price_inr: int
    currency: str
    status: str
    created_at: Optional[str] = None


class DesktopCheckoutContextOut(BaseModel):
    """Authenticated buyer identity for checkout confirmation (no secrets)."""

    user_id: int
    email: str
    company_id: int
    company_name: str


class LicenseKeyMaterialOut(BaseModel):
    """Internal mint result — plaintext returned once to caller; never log it."""

    plaintext: str
    key_hash: str
    key_encrypted: Optional[str]
    key_prefix: str
    key_last4: str
    key_masked: str


class MachineApiStubOut(BaseModel):
    """Phase 1 placeholder until Phase 7 implements Ed25519 machine APIs."""

    phase: str = "1-foundation"
    implemented: bool = False
    detail: str
