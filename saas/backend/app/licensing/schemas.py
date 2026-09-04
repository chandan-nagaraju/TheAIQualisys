"""Pydantic schemas for desktop licensing (Phase 1 foundation)."""

from __future__ import annotations

from datetime import datetime
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


class LicensingHealthOut(BaseModel):
    enabled: bool
    products_seeded: int
    plans_seeded: int
    phase: str = "1-foundation"
    message: str


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
