from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# This file: saas/backend/app/config.py → backend root = parents[1]
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_BACKEND_TEMPLATES_ROOT = _BACKEND_ROOT / "templates"
_BACKEND_STATIC_ROOT = _BACKEND_ROOT / "static"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = Field(
        default="postgresql+psycopg2://fir:fir@localhost:5432/fir_saas",
        validation_alias=AliasChoices("DATABASE_URL", "database_url"),
    )

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, v: object) -> object:
        """Render/Neon often use postgres:// or postgresql:// without the psycopg2 driver prefix."""
        if not isinstance(v, str):
            return v
        if v.startswith("postgres://"):
            return "postgresql+psycopg2://" + v[len("postgres://") :]
        if v.startswith("postgresql://") and not v.startswith("postgresql+"):
            return "postgresql+psycopg2://" + v[len("postgresql://") :]
        return v
    jwt_secret: str = "change-me-in-production-use-long-random"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7

    admin_jwt_secret: str = "change-me-admin-jwt-separate"
    admin_access_token_expire_minutes: int = 60 * 8

    # When False: skip invoice/FIR monthly-cap checks in API (dev convenience). FIR workspace access
    # still requires a valid trial or active paid window (see can_access_fir_workspace).
    # Production: set True (env ENABLE_SUBSCRIPTION=true).
    enable_subscription: bool = Field(
        default=True,
        validation_alias=AliasChoices("ENABLE_SUBSCRIPTION", "enable_subscription"),
    )

    upi_id: str = "chandanregins1@okaxis"
    whatsapp_number: str = "917892007580"
    whatsapp_message_template: str = (
        "Pay via UPI: {upi_id} and send screenshot on WhatsApp"
    )

    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        validation_alias=AliasChoices("CORS_ORIGINS", "cors_origins"),
    )

    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: str | None = None

    # Workspace uploads (per-company FIR files) under saas/backend/uploads/
    workspace_upload_dir: Path = Field(default=_BACKEND_ROOT / "uploads")
    templates_dir: Path = Field(default=_BACKEND_TEMPLATES_ROOT)
    static_dir: Path = Field(default=_BACKEND_STATIC_ROOT)
    backend_root: Path = Field(default=_BACKEND_ROOT)

    # Public SPA origin for password-reset links, e.g. http://localhost:5173
    public_app_url: str = Field(
        default="http://localhost:5173",
        validation_alias=AliasChoices("PUBLIC_APP_URL", "public_app_url"),
    )

    smtp_host: str | None = Field(default=None, validation_alias=AliasChoices("SMTP_HOST", "smtp_host"))
    smtp_port: int = Field(default=587, validation_alias=AliasChoices("SMTP_PORT", "smtp_port"))
    smtp_use_tls: bool = Field(default=True, validation_alias=AliasChoices("SMTP_USE_TLS", "smtp_use_tls"))
    smtp_use_ssl: bool = Field(default=False, validation_alias=AliasChoices("SMTP_USE_SSL", "smtp_use_ssl"))
    smtp_user: str | None = Field(default=None, validation_alias=AliasChoices("SMTP_USER", "smtp_user"))
    smtp_password: str | None = Field(default=None, validation_alias=AliasChoices("SMTP_PASSWORD", "smtp_password"))
    email_from: str | None = Field(default=None, validation_alias=AliasChoices("EMAIL_FROM", "email_from"))

    # S3 direct uploads for workspace company assets (optional — when unset, settings use DB blobs / local files).
    aws_access_key_id: str | None = Field(default=None, validation_alias=AliasChoices("AWS_ACCESS_KEY_ID"))
    aws_secret_access_key: str | None = Field(
        default=None, validation_alias=AliasChoices("AWS_SECRET_ACCESS_KEY")
    )
    aws_region: str | None = Field(default=None, validation_alias=AliasChoices("AWS_REGION"))
    s3_bucket_name: str | None = Field(default=None, validation_alias=AliasChoices("S3_BUCKET_NAME"))
    public_s3_base_url: str | None = Field(default=None, validation_alias=AliasChoices("PUBLIC_S3_BASE_URL"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
