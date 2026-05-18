from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PlanType(str, enum.Enum):
    basic = "basic"
    pro = "pro"
    enterprise = "enterprise"


class SubscriptionStatus(str, enum.Enum):
    trial = "trial"
    active = "active"
    expired = "expired"


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    vendor_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    trial_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    trial_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    subscription_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    subscription_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Local calendar day (SUBSCRIPTION_REMINDER_TIMEZONE) for which subscription_expiry_reminder_mask applies.
    subscription_expiry_reminder_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Bit 1 = morning reminder sent; bit 2 = evening reminder sent (reset when reminder_date != today_local).
    subscription_expiry_reminder_mask: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    plan_type: Mapped[str] = mapped_column(String(32), nullable=False, default=PlanType.basic.value)
    subscription_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=SubscriptionStatus.trial.value
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    users: Mapped[list[CompanyUser]] = relationship("CompanyUser", back_populates="company")
    invoices: Mapped[list[InvoiceV2]] = relationship("InvoiceV2", back_populates="company")
    parts: Mapped[list[PartV2]] = relationship("PartV2", back_populates="company")
    customers: Mapped[list["Customer"]] = relationship("Customer", back_populates="company")
    fir_settings: Mapped["CompanySettings | None"] = relationship(
        "CompanySettings", back_populates="company", uselist=False
    )
    fir_report_events: Mapped[list["FirReportEvent"]] = relationship(
        "FirReportEvent", back_populates="company", cascade="all, delete-orphan"
    )
    fir_upload_logs: Mapped[list["FirUploadLog"]] = relationship(
        "FirUploadLog", back_populates="company", cascade="all, delete-orphan"
    )


class CompanyUser(Base):
    __tablename__ = "company_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_blocked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    company: Mapped[Company] = relationship("Company", back_populates="users")


class PlatformAdmin(Base):
    __tablename__ = "platform_admins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("company_users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[CompanyUser] = relationship("CompanyUser")


class AdminPasswordResetToken(Base):
    __tablename__ = "admin_password_reset_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_id: Mapped[int] = mapped_column(
        ForeignKey("platform_admins.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    admin: Mapped[PlatformAdmin] = relationship("PlatformAdmin")


class InvoiceV2(Base):
    __tablename__ = "invoices_v2"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    invoice_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    company: Mapped[Company] = relationship("Company", back_populates="invoices")


class PartV2(Base):
    __tablename__ = "parts_v2"
    __table_args__ = (
        UniqueConstraint("company_id", "customer_id", "part_no", name="uq_parts_v2_company_customer_part"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("fir_customers.id", ondelete="RESTRICT"), nullable=False, index=True)
    part_no: Mapped[str] = mapped_column(String(255), nullable=False)
    drawing_rev: Mapped[str | None] = mapped_column(String(128), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    drawing_pdf_filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    drawing_pdf_mime: Mapped[str | None] = mapped_column(String(128), nullable=True)
    drawing_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    company: Mapped[Company] = relationship("Company", back_populates="parts")
    customer: Mapped["Customer"] = relationship("Customer", back_populates="parts")
    specs: Mapped[list[PartSpecV2]] = relationship(
        "PartSpecV2", back_populates="part", cascade="all, delete-orphan"
    )
    complaints: Mapped[list["PartComplaintV2"]] = relationship(
        "PartComplaintV2", back_populates="part", cascade="all, delete-orphan"
    )
    materials: Mapped[list["PartMaterialV2"]] = relationship(
        "PartMaterialV2", back_populates="part", cascade="all, delete-orphan"
    )
    coatings: Mapped[list["PartCoatingV2"]] = relationship(
        "PartCoatingV2", back_populates="part", cascade="all, delete-orphan"
    )
    revision_history: Mapped[list["PartRevisionHistory"]] = relationship(
        "PartRevisionHistory", back_populates="part", cascade="all, delete-orphan"
    )


class PartRevisionHistory(Base):
    __tablename__ = "part_revision_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    part_id: Mapped[int] = mapped_column(ForeignKey("parts_v2.id", ondelete="CASCADE"), nullable=False, index=True)
    previous_rev: Mapped[str | None] = mapped_column(String(128), nullable=True)
    new_rev: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    changed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("company_users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    part: Mapped[PartV2] = relationship("PartV2", back_populates="revision_history")


class PartSpecV2(Base):
    __tablename__ = "part_specs_v2"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    part_id: Mapped[int] = mapped_column(ForeignKey("parts_v2.id", ondelete="CASCADE"), nullable=False, index=True)
    parameter: Mapped[str] = mapped_column(String(512), nullable=False)
    specification: Mapped[str | None] = mapped_column(Text, nullable=True)
    special_char: Mapped[str | None] = mapped_column(String(255), nullable=True)
    method_of_inspection: Mapped[str | None] = mapped_column(String(255), nullable=True)

    part: Mapped[PartV2] = relationship("PartV2", back_populates="specs")


class Customer(Base):
    __tablename__ = "fir_customers"
    __table_args__ = (UniqueConstraint("company_id", "vendor_code", name="uq_fir_customer_vendor"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    vendor_code: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    company: Mapped[Company] = relationship("Company", back_populates="customers")
    fir_report_events: Mapped[list["FirReportEvent"]] = relationship(
        "FirReportEvent", back_populates="customer"
    )
    parts: Mapped[list["PartV2"]] = relationship("PartV2", back_populates="customer")


class FirReportEvent(Base):
    """Unique business event per invoice line (deduped via event_uid) for FIR Intelligence analytics."""

    __tablename__ = "fir_events"
    __table_args__ = (UniqueConstraint("event_uid", name="fir_events_event_uid_unique"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("fir_customers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    part_no: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    invoice_no: Mapped[str | None] = mapped_column(String(128), nullable=True)
    event_uid: Mapped[str] = mapped_column(String(64), nullable=False)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    quantity: Mapped[str] = mapped_column(String(64), nullable=False)
    source_file: Mapped[str | None] = mapped_column(String(512), nullable=True)
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    company: Mapped[Company] = relationship("Company", back_populates="fir_report_events")
    customer: Mapped[Customer | None] = relationship("Customer", back_populates="fir_report_events")


class FirUploadLog(Base):
    """Optional per-upload summary for FIR Intelligence ingestion."""

    __tablename__ = "fir_upload_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    rows_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    new_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reports_generated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    company: Mapped[Company] = relationship("Company", back_populates="fir_upload_logs")


class CompanySettings(Base):
    """Per-company FIR header / document settings (legacy Settings row)."""

    __tablename__ = "company_settings"

    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True
    )
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    logo_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    inspector_signature_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    quality_signature_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    logo_blob: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    logo_mime: Mapped[str | None] = mapped_column(String(128), nullable=True)
    inspector_signature_blob: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    inspector_signature_mime: Mapped[str | None] = mapped_column(String(128), nullable=True)
    quality_signature_blob: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    quality_signature_mime: Mapped[str | None] = mapped_column(String(128), nullable=True)
    quali_font_blob: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    quali_font_mime: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # S3 object key (company/{id}/...) when custom font is stored in object storage.
    quali_font_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    format_no: Mapped[str | None] = mapped_column(String(128), nullable=True)
    issue_date: Mapped[str | None] = mapped_column(String(64), nullable=True)
    doc_rev_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rev_date: Mapped[str | None] = mapped_column(String(64), nullable=True)

    company: Mapped[Company] = relationship("Company", back_populates="fir_settings")


class PartComplaintV2(Base):
    __tablename__ = "part_complaints_v2"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    part_id: Mapped[int] = mapped_column(ForeignKey("parts_v2.id", ondelete="CASCADE"), nullable=False, index=True)
    parameter: Mapped[str] = mapped_column(String(512), nullable=False)
    specification: Mapped[str | None] = mapped_column(Text, nullable=True)
    special_char: Mapped[str | None] = mapped_column(String(255), nullable=True)
    method_of_inspection: Mapped[str | None] = mapped_column(String(255), nullable=True)

    part: Mapped[PartV2] = relationship("PartV2", back_populates="complaints")


class PartMaterialV2(Base):
    __tablename__ = "part_materials_v2"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    part_id: Mapped[int] = mapped_column(ForeignKey("parts_v2.id", ondelete="CASCADE"), nullable=False, index=True)
    material_grade: Mapped[str] = mapped_column(String(255), nullable=False)

    part: Mapped[PartV2] = relationship("PartV2", back_populates="materials")


class PartCoatingV2(Base):
    __tablename__ = "part_coatings_v2"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    part_id: Mapped[int] = mapped_column(ForeignKey("parts_v2.id", ondelete="CASCADE"), nullable=False, index=True)
    parameter: Mapped[str] = mapped_column(String(512), nullable=False)
    specification: Mapped[str | None] = mapped_column(Text, nullable=True)
    special_char: Mapped[str | None] = mapped_column(String(255), nullable=True)
    method_of_inspection: Mapped[str | None] = mapped_column(String(255), nullable=True)

    part: Mapped[PartV2] = relationship("PartV2", back_populates="coatings")


class ModuleSubscription(Base):
    """Per-user subscription to a QMS product module (not FIR billing plans)."""

    __tablename__ = "module_subscriptions"
    __table_args__ = (UniqueConstraint("user_id", "module_name", name="uq_module_subscriptions_user_module"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("company_users.id", ondelete="CASCADE"), nullable=False, index=True)
    module_name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ModuleTrial(Base):
    __tablename__ = "module_trials"
    __table_args__ = (UniqueConstraint("user_id", "module_name", name="uq_module_trials_user_module"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("company_users.id", ondelete="CASCADE"), nullable=False, index=True)
    module_name: Mapped[str] = mapped_column(String(64), nullable=False)
    trial_start: Mapped[date] = mapped_column(Date, nullable=False)
    trial_end: Mapped[date] = mapped_column(Date, nullable=False)
    usage_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    actions_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ModulePricing(Base):
    """Admin-configurable prices, FIR usage caps, and QMS trial defaults."""

    __tablename__ = "module_pricing"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    module_name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    monthly_price: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    yearly_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trial_days: Mapped[int] = mapped_column(Integer, nullable=False, default=14)
    usage_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    fir_plan_type: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    invoice_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    invoice_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    highlight: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    listing_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
