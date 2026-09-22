from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.part_field_validation import sanitize_part_master_alnum_upper, sanitize_part_master_description


class RequestSignupVerificationBody(BaseModel):
    company_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    vendor_code: str = Field(min_length=2, max_length=64)


class VerifySignupSuccessResponse(BaseModel):
    ok: bool = True
    company_name: str
    email: str
    vendor_code: str


class CompleteSignupBody(BaseModel):
    token: str = Field(min_length=1, max_length=512)
    password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)


class SignupVerificationSentResponse(BaseModel):
    message: str


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
    trial_start_date: date | None
    trial_end_date: date | None
    subscription_start: date | None
    subscription_end: date | None
    plan_type: str
    subscription_status: str
    billing_address: str | None = None
    billing_city: str | None = None
    billing_state: str | None = None
    billing_state_code: str | None = None
    billing_pincode: str | None = None
    gstin: str | None = None
    phone: str | None = None

    model_config = {"from_attributes": True}


class CompanyBillingProfileIn(BaseModel):
    """Buyer (customer company) details stored on companies — used on subscription invoices."""

    company_name: str = Field(min_length=1, max_length=255)
    billing_address: str | None = None
    billing_city: str | None = None
    billing_state: str | None = None
    billing_state_code: str | None = None
    billing_pincode: str | None = None
    gstin: str | None = None
    phone: str | None = None


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
        s = sanitize_part_master_description(v if isinstance(v, str) else str(v))
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


class PlatformAdminOut(BaseModel):
    id: int
    email: str
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class PlatformAdminCreateBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def _passwords_match(self):
        if self.password != self.confirm_password:
            raise ValueError("password and confirm_password must match")
        return self


class PlatformAdminSetPasswordBody(BaseModel):
    password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def _passwords_match(self):
        if self.password != self.confirm_password:
            raise ValueError("password and confirm_password must match")
        return self


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


class AdminBillingPaymentOut(BaseModel):
    id: int
    payment_code: str | None = None
    company_id: int
    user_id: int | None
    customer_id: int | None = None
    customer_name: str | None
    company_name: str | None
    email: str | None
    phone: str | None
    billing_address: str | None = None
    city: str | None = None
    state: str | None = None
    state_code: str | None = None
    pincode: str | None = None
    gstin: str | None = None
    module_key: str | None = None
    module_label: str | None = None
    subscription_plan: str
    plan_type: str | None = None
    plan_id: int | None = None
    billing_period: str | None = None
    billing_period_label: str | None = None
    subscription_duration: str | None = None
    subscription_start: str | None
    subscription_end: str | None
    subscription_start_date: str | None = None
    subscription_end_date: str | None = None
    amount_inr: float
    currency: str | None = "INR"
    original_plan_price: int | None = None
    payment_method: str
    reference_note: str | None
    payment_date: str | None
    payment_submitted_at: str | None = None
    status: str
    has_proof: bool
    pricing_snapshot: dict | None = None
    verified_at: str | None = None
    payment_verified_at: str | None = None
    rejected_at: str | None = None
    rejection_reason: str | None = None
    rejection_reason_label: str | None = None
    whatsapp_number: str | None = None
    whatsapp_url: str | None = None
    invoice_id: int | None = None
    invoice_number: str | None = None
    invoice_status: str | None = None


class AdminBillingPaymentListResponse(BaseModel):
    pending_count: int
    verified_count: int
    rejected_count: int
    items: list[AdminBillingPaymentOut]


class AdminBillingPaymentRejectBody(BaseModel):
    reason: str
    note: str | None = None


class AdminNotificationOut(BaseModel):
    id: int
    title: str
    message: str
    link_path: str
    payment_id: int | None
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class PaymentQuoteRequest(BaseModel):
    module_key: str = "fir"
    plan_type: str | None = None
    billing_period: str


class PaymentDoneRequest(BaseModel):
    module_key: str = "fir"
    plan_type: str | None = None
    billing_period: str


class PaymentDoneResponse(BaseModel):
    payment_id: int
    payment_code: str | None
    status: str
    already_submitted: bool
    amount_inr: float
    currency: str
    module_label: str | None
    plan_name: str
    billing_period_label: str | None
    whatsapp_url: str
    whatsapp_message: str
    message: str


class PaymentQuoteOut(BaseModel):
    module_key: str
    module_label: str
    plan_type: str
    plan_name: str
    billing_period: str
    billing_period_label: str
    subscription_duration: str
    amount_inr: float
    taxable_amount_inr: float
    gst_rate: float = 18
    gst_amount_inr: float
    currency: str
    monthly_price: int
    payment_method: str


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
        description="activate | extend | extend_trial | set_plan | mark_expired | set_billing_profile",
    )
    subscription_end: date | None = None
    subscription_start: date | None = None
    trial_start_date: date | None = None
    trial_end_date: date | None = None
    plan_type: str | None = None
    extend_days: int | None = None
    billing_address: str | None = None
    billing_city: str | None = None
    billing_state: str | None = None
    billing_state_code: str | None = None
    billing_pincode: str | None = None
    gstin: str | None = None
    phone: str | None = None


ThankYouCategory = Literal["running", "regular", "occasional", "stranger", "new", "all"]


class AdminSubscriptionReminderSendBody(BaseModel):
    reminder_type: Literal["ending_soon", "already_ended", "thank_you", "trial_ending"]
    thank_you_category: ThankYouCategory | None = None

    @model_validator(mode="after")
    def _thank_you_needs_category(self):
        if self.reminder_type == "thank_you":
            if self.thank_you_category is None:
                raise ValueError("thank_you_category is required when reminder_type is thank_you")
        elif self.thank_you_category is not None:
            raise ValueError("thank_you_category is only allowed when reminder_type is thank_you")
        return self


class AdminSubscriptionReminderSendResponse(BaseModel):
    ok: bool = True
    email_status: str
    total_report_count: int
    current_month_report_count: int
    current_month_name: str
    recipients_attempted: int
    emails_sent: int


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


class AdminBillingSettingsIn(BaseModel):
    business_name: str | None = None
    business_address: str | None = None
    gstin: str | None = None
    state: str | None = None
    state_code: str | None = None
    email: str | None = None
    phone: str | None = None
    logo_path: str | None = None
    invoice_prefix: str | None = None
    cgst_rate: float | None = None
    sgst_rate: float | None = None
    igst_rate: float | None = None
    terms_notes: str | None = None


class AdminBillingSettingsOut(AdminBillingSettingsIn):
    pass


class AdminBillingInvoiceGenerateBody(BaseModel):
    payment_id: int


class AdminBillingInvoiceOut(BaseModel):
    id: int
    invoice_id: str | None = None
    invoice_number: str
    payment_id: int
    payment_code: str | None = None
    customer_id: int | None = None
    company_id: int
    user_id: int | None = None
    module_id: int | None = None
    module_key: str | None = None
    module_name: str | None = None
    plan_id: int | None = None
    plan_name: str
    billing_period: str | None = None
    billing_period_label: str | None = None
    invoice_date: str | None = None
    subscription_start_date: str | None = None
    subscription_end_date: str | None = None
    subtotal: float
    taxable_amount: float
    cgst: float
    sgst: float
    igst: float
    total_tax: float
    grand_total: float
    currency: str | None = "INR"
    tax_mode: str | None = None
    cgst_rate: float | None = None
    sgst_rate: float | None = None
    igst_rate: float | None = None
    status: str
    pdf_path: str | None = None
    line_description: str | None = None
    customer_name: str | None = None
    company_name: str | None = None
    email: str | None = None
    phone: str | None = None
    billing_address: str | None = None
    city: str | None = None
    state: str | None = None
    state_code: str | None = None
    pincode: str | None = None
    gstin: str | None = None
    payment_method: str | None = None
    payment_reference: str | None = None
    payment_verified_at: str | None = None
    seller: dict | None = None
    vendor_code: str | None = None
    hsn_sac: str | None = None
    uom: str | None = None
    quantity: int | None = 1
    rate: float | None = None
    terms_notes: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class AdminBillingInvoiceListResponse(BaseModel):
    total_count: int
    draft_count: int
    generated_count: int
    cancelled_count: int
    items: list[AdminBillingInvoiceOut]
