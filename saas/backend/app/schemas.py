from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.part_field_validation import sanitize_part_master_alnum_upper


class SignupRequest(BaseModel):
    company_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    vendor_code: str = Field(min_length=2, max_length=64)


class LoginRequest(BaseModel):
    identifier: str = Field(description="Email or vendor_code")
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UnifiedLoginResponse(BaseModel):
    """Same login form: platform admin (email) or company user (email or vendor code)."""

    access_token: str
    token_type: str = "bearer"
    role: str = Field(description="platform_admin | company")


class CompanyUserOut(BaseModel):
    id: int
    email: str
    name: str | None
    company_id: int

    model_config = {"from_attributes": True}


class CompanyOut(BaseModel):
    id: int
    company_name: str
    vendor_code: str
    trial_start_date: date
    trial_end_date: date
    subscription_start: date | None
    subscription_end: date | None
    plan_type: str
    subscription_status: str

    model_config = {"from_attributes": True}


class MeResponse(BaseModel):
    user: CompanyUserOut
    company: CompanyOut
    invoices_this_month: int
    fir_reports_this_month: int
    usage_this_month: int
    invoice_limit: int | None
    can_create_invoice: bool
    can_record_fir_report: bool
    trial_active: bool
    subscription_active: bool
    can_access_fir_workspace: bool
    subscription_message: str | None = None


class SubscriptionStatusResponse(BaseModel):
    enable_subscription: bool
    company: CompanyOut
    invoices_this_month: int
    fir_reports_this_month: int
    usage_this_month: int
    invoice_limit: int | None
    can_create_invoice: bool
    can_record_fir_report: bool
    trial_active: bool
    subscription_active: bool
    can_access_fir_workspace: bool
    trial_days_remaining: int | None = None
    subscription_days_remaining: int | None = None


class PlanInfo(BaseModel):
    plan_type: str
    name: str
    price_inr: int
    min_invoices: int
    max_invoices: int | None
    highlight: str | None = None


class UpgradeInfoResponse(BaseModel):
    upi_id: str
    whatsapp_url: str
    message: str


class InvoiceCreateV2(BaseModel):
    invoice_number: str | None = None


class InvoiceOutV2(BaseModel):
    id: int
    company_id: int
    invoice_number: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PartCreateV2(BaseModel):
    part_no: str
    drawing_rev: str | None = None
    description: str | None = None

    @field_validator("part_no", mode="before")
    @classmethod
    def _part_no_alnum_upper(cls, v: object) -> str:
        return sanitize_part_master_alnum_upper(v if isinstance(v, str) else (str(v) if v is not None else None))

    @field_validator("description", mode="before")
    @classmethod
    def _description_alnum_upper(cls, v: object) -> str | None:
        if v is None:
            return None
        s = sanitize_part_master_alnum_upper(v if isinstance(v, str) else str(v))
        return s if s else None

    @field_validator("part_no")
    @classmethod
    def _part_no_required(cls, v: str) -> str:
        if not v:
            raise ValueError("part_no must contain at least one letter or digit (A–Z, 0–9)")
        return v


class PartOutV2(BaseModel):
    id: int
    company_id: int
    part_no: str
    drawing_rev: str | None
    description: str | None

    model_config = {"from_attributes": True}


class SpecOutV2(BaseModel):
    id: int
    part_id: int
    parameter: str
    specification: str | None
    special_char: str | None
    method_of_inspection: str | None

    model_config = {"from_attributes": True}


class AdminLoginRequest(BaseModel):
    email: EmailStr
    password: str


class AdminCompanySummary(BaseModel):
    id: int
    company_name: str
    vendor_code: str
    plan_type: str
    subscription_status: str
    monthly_usage: int
    monthly_fir_reports: int
    monthly_usage_combined: int
    tenant_user_count: int = 0


class AdminDashboardResponse(BaseModel):
    total_companies: int
    trial_count: int
    active_count: int
    expired_count: int
    total_invoices: int


class AdminTenantUserRow(BaseModel):
    """Company login accounts (who uses the FIR workspace) — cross-tenant."""

    user_id: int
    email: str
    name: str | None
    created_at: datetime
    company_id: int
    company_name: str
    company_vendor_code: str
    plan_type: str
    subscription_status: str
    is_blocked: bool


class AdminFirCustomerRow(BaseModel):
    """FIR customer/vendor rows (upload context) per tenant."""

    customer_id: int
    vendor_code: str
    name: str
    company_id: int
    company_name: str
    company_vendor_code: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=16, max_length=512)
    new_password: str = Field(min_length=8, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class AdminCompanyPatch(BaseModel):
    action: str = Field(
        description="activate | extend | set_plan | mark_expired",
    )
    subscription_end: date | None = None
    subscription_start: date | None = None
    plan_type: str | None = None
    extend_days: int | None = None


class QmsModuleOverviewItem(BaseModel):
    slug: str
    module_name: str
    access: str
    badge: str
    actions_remaining: int | None = None
    days_remaining: int | None = None
    trial_expired_message: str | None = None
    notify_trial_ending: bool = False


class QmsModuleOverviewResponse(BaseModel):
    modules: list[QmsModuleOverviewItem]


class QmsModuleSessionResponse(BaseModel):
    module_name: str
    slug: str
    access: str
    actions_remaining: int | None = None
    days_remaining: int | None = None


class QmsModuleConsumeResponse(BaseModel):
    ok: bool
    access: str
    actions_remaining: int | None = None
    days_remaining: int | None = None


class ModulePricingPublicOut(BaseModel):
    module_name: str
    display_name: str
    monthly_price: int
    yearly_price: int | None = None
    trial_days: int
    usage_limit: int
    fir_plan_type: str | None = None
    invoice_min: int | None = None
    invoice_max: int | None = None
    highlight: str | None = None
    sort_order: int
    listing_active: bool = False

    model_config = {"from_attributes": True}


class ModulePricingPatch(BaseModel):
    display_name: str | None = Field(default=None, max_length=255)
    monthly_price: int | None = Field(default=None, ge=0)
    yearly_price: int | None = Field(default=None, ge=0)
    trial_days: int | None = Field(default=None, ge=0, le=3650)
    usage_limit: int | None = Field(default=None, ge=0, le=1_000_000)
    invoice_min: int | None = Field(default=None, ge=0)
    invoice_max: int | None = None
    highlight: str | None = Field(default=None, max_length=255)
    sort_order: int | None = Field(default=None, ge=0)
    listing_active: bool | None = None


class BillingModuleRow(BaseModel):
    module_key: str
    display_name: str
    subscription_status: str
    reports_this_month: int | None = None
    combined_usage_this_month: int | None = None
    usage_limit: int | None = None
    remaining: int | None = None
    trial_actions_used: int | None = None
    trial_actions_limit: int | None = None
    trial_actions_remaining: int | None = None


class BillingOverviewResponse(BaseModel):
    company_name: str
    vendor_code: str
    plan_name: str
    enable_subscription: bool = True
    company_status: str
    trial_end_date: date | None = None
    subscription_start: date | None = None
    subscription_end: date | None = None
    modules: list[BillingModuleRow]
    can_access_fir_workspace: bool
    subscription_message: str | None = None
