"""ORM models for desktop product licensing (additive; FIR/QMS untouched)."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DesktopProduct(Base):
    __tablename__ = "desktop_products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    listing_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    trial_enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    trial_duration_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    buy_url_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    plans: Mapped[list["DesktopPlan"]] = relationship("DesktopPlan", back_populates="product")


class DesktopPlan(Base):
    __tablename__ = "desktop_plans"
    __table_args__ = (UniqueConstraint("product_id", "code", name="uq_desktop_plans_product_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("desktop_products.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_inr: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False, default=365)
    seats: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    listing_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    product: Mapped[DesktopProduct] = relationship("DesktopProduct", back_populates="plans")


class DesktopOrder(Base):
    __tablename__ = "desktop_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("company_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("desktop_products.id", ondelete="RESTRICT"), nullable=False
    )
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("desktop_plans.id", ondelete="RESTRICT"), nullable=False
    )
    # Catalog snapshots at order time (historical price/name integrity)
    product_code: Mapped[str] = mapped_column(String(64), nullable=False)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    plan_code: Mapped[str] = mapped_column(String(64), nullable=False)
    plan_name: Mapped[str] = mapped_column(String(255), nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    seats: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price_inr: Mapped[int] = mapped_column(Integer, nullable=False)
    total_price_inr: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="INR")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending_payment", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    payments: Mapped[list["DesktopPayment"]] = relationship("DesktopPayment", back_populates="order")


class DesktopPayment(Base):
    __tablename__ = "desktop_payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("desktop_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    upi_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    amount_inr: Mapped[int] = mapped_column(Integer, nullable=False)
    reference_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    screenshot_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    screenshot_mime: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="submitted")
    reviewed_by_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("platform_admins.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    order: Mapped[DesktopOrder] = relationship("DesktopOrder", back_populates="payments")


class DesktopDevice(Base):
    __tablename__ = "desktop_devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fingerprint_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    fingerprint_raw_hint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    os_meta: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DesktopLicense(Base):
    __tablename__ = "desktop_licenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("desktop_products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("desktop_plans.id", ondelete="SET NULL"), nullable=True
    )
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("desktop_orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    licensed_user_id: Mapped[int] = mapped_column(
        ForeignKey("company_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entitlement_type: Mapped[str] = mapped_column(String(16), nullable=False, default="paid", index=True)
    seat_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    key_prefix: Mapped[str] = mapped_column(String(64), nullable=False)
    key_last4: Mapped[str] = mapped_column(String(8), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="issued", index=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    bound_device_id: Mapped[int | None] = mapped_column(
        ForeignKey("desktop_devices.id", ondelete="SET NULL"), nullable=True
    )
    created_by_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("platform_admins.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DesktopActivation(Base):
    __tablename__ = "desktop_activations"
    __table_args__ = (
        UniqueConstraint("license_id", "device_id", name="uq_desktop_activations_license_device"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    license_id: Mapped[int] = mapped_column(
        ForeignKey("desktop_licenses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("company_users.id", ondelete="CASCADE"), nullable=False
    )
    device_id: Mapped[int] = mapped_column(
        ForeignKey("desktop_devices.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    app_version: Mapped[str | None] = mapped_column(String(64), nullable=True)


class DesktopLicenseEvent(Base):
    __tablename__ = "desktop_license_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    license_id: Mapped[int | None] = mapped_column(
        ForeignKey("desktop_licenses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    meta_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DesktopInstaller(Base):
    __tablename__ = "desktop_installers"
    __table_args__ = (
        UniqueConstraint("product_id", "version", name="uq_desktop_installers_product_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("desktop_products.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    release_channel: Mapped[str] = mapped_column(String(32), nullable=False, default="current")
    min_supported_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    min_windows_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    storage_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_sha256: Mapped[str | None] = mapped_column(String(128), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    release_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    release_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    listing_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DesktopDownloadToken(Base):
    __tablename__ = "desktop_download_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("company_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    installer_id: Mapped[int] = mapped_column(
        ForeignKey("desktop_installers.id", ondelete="CASCADE"), nullable=False
    )
    license_id: Mapped[int | None] = mapped_column(
        ForeignKey("desktop_licenses.id", ondelete="SET NULL"), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
