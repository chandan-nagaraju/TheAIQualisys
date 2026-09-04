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
    phase: str = "6-protected-downloads"
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


class DesktopUpiSettingsOut(BaseModel):
    upi_id: str
    payee_name: str
    instructions: Optional[str] = None
    has_qr_image: bool = False


class DesktopUpiSettingsAdminOut(DesktopUpiSettingsOut):
    qr_image_path: Optional[str] = None
    updated_at: Optional[str] = None


class DesktopUpiSettingsPatch(BaseModel):
    upi_id: str = Field(min_length=3, max_length=255)
    payee_name: str = Field(min_length=1, max_length=255)
    instructions: Optional[str] = None
    clear_qr: bool = False


class DesktopPaymentOut(BaseModel):
    id: int
    order_id: int
    upi_id: Optional[str] = None
    amount_inr: int
    reference_note: Optional[str] = None
    has_screenshot: bool = False
    screenshot_mime: Optional[str] = None
    status: str
    reviewed_by_admin_id: Optional[int] = None
    reviewed_at: Optional[str] = None
    review_note: Optional[str] = None
    created_at: Optional[str] = None


class DesktopPaymentRejectBody(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)


class DesktopLicenseMintSummaryOut(BaseModel):
    """Phase 4: no plaintext keys — seat summaries only (email/reveal in Phase 5)."""

    id: int
    seat_index: Optional[int] = None
    product_id: int
    status: str
    key_prefix: str
    key_last4: str
    bound_device_id: Optional[int] = None
    expires_at: Optional[str] = None


class DesktopPaymentApproveOut(BaseModel):
    payment: DesktopPaymentOut
    order: DesktopOrderOut
    licenses_minted: int
    licenses: List[DesktopLicenseMintSummaryOut]
    email_delivery: Optional["DesktopLicenseEmailDeliveryOut"] = None


class DesktopLicenseOut(BaseModel):
    """Masked license for list/detail — never includes plaintext or ciphertext."""

    id: int
    product_id: int
    plan_id: Optional[int] = None
    order_id: Optional[int] = None
    company_id: int
    licensed_user_id: int
    entitlement_type: str
    seat_index: Optional[int] = None
    status: str
    key_masked: str
    key_prefix: str
    key_last4: str
    issued_at: Optional[str] = None
    expires_at: Optional[str] = None
    activated_at: Optional[str] = None
    bound_device_id: Optional[int] = None
    device_status: str
    is_activated: bool = False
    order_number: Optional[str] = None
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    plan_code: Optional[str] = None
    plan_name: Optional[str] = None
    duration_days: Optional[int] = None
    order_seats: Optional[int] = None
    email_status: Optional[str] = None
    email_sent_at: Optional[str] = None


class DesktopLicenseRevealOut(BaseModel):
    """Authorized reveal — plaintext only; no ciphertext / secrets."""

    license_id: int
    seat_index: Optional[int] = None
    license_key: str
    key_masked: str


class DesktopLicenseEmailDeliveryOut(BaseModel):
    id: int
    order_id: int
    status: str
    attempt_count: int
    last_attempted_at: Optional[str] = None
    sent_at: Optional[str] = None
    last_error: Optional[str] = None
    to_email: str


class DesktopInstallerCreate(BaseModel):
    version: str = Field(min_length=1, max_length=64)
    release_notes: Optional[str] = None
    release_date: Optional[str] = None  # ISO date
    min_windows_version: Optional[str] = None
    min_supported_version: Optional[str] = None


class DesktopInstallerPatch(BaseModel):
    release_notes: Optional[str] = None
    release_date: Optional[str] = None
    min_windows_version: Optional[str] = None
    min_supported_version: Optional[str] = None
    clear_notes: bool = False


class DesktopInstallerChannelBody(BaseModel):
    channel: str = Field(min_length=3, max_length=32)


class DesktopInstallerAdminOut(BaseModel):
    id: int
    product_id: int
    version: str
    release_channel: str
    listing_active: bool
    min_supported_version: Optional[str] = None
    min_windows_version: Optional[str] = None
    file_name: Optional[str] = None
    file_sha256: Optional[str] = None
    file_size_bytes: Optional[int] = None
    release_date: Optional[str] = None
    release_notes: Optional[str] = None
    has_file: bool = False
    storage_key: Optional[str] = None
    created_at: Optional[str] = None
    product_code: Optional[str] = None
    product_name: Optional[str] = None


class DesktopInstallerCustomerOut(BaseModel):
    id: int
    product_id: int
    product_code: str
    product_name: str
    version: str
    release_channel: str
    is_current: bool = False
    is_recommended: bool = False
    is_mandatory: bool = False
    min_windows_version: Optional[str] = None
    file_name: Optional[str] = None
    file_sha256: Optional[str] = None
    file_size_bytes: Optional[int] = None
    release_date: Optional[str] = None
    release_notes: Optional[str] = None


class DesktopDownloadProductOut(BaseModel):
    product_id: int
    product_code: str
    product_name: str
    current: Optional[DesktopInstallerCustomerOut] = None
    recommended: Optional[DesktopInstallerCustomerOut] = None
    versions: List[DesktopInstallerCustomerOut] = Field(default_factory=list)


class DesktopDownloadTokenOut(BaseModel):
    token: str
    expires_in_seconds: int
    installer_id: int


class DesktopDownloadRedeemOut(BaseModel):
    download_url: str
    expires_in_seconds: int
    file_name: Optional[str] = None
    file_sha256: Optional[str] = None
    file_size_bytes: Optional[int] = None


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
