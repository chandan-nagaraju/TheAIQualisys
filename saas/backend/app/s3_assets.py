"""Presigned S3 uploads for company FIR settings assets (logos, signatures, fonts)."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from botocore.config import Config

from app.config import Settings

SettingsAssetKind = Literal["logo", "inspector_signature", "quality_signature", "quali_font"]

_KIND_PREFIX = {
    "logo": "logo",
    "inspector_signature": "inspector-signature",
    "quality_signature": "quality-signature",
    "quali_font": "quali-font",
}

_IMAGE_CT = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"})
_FONT_CT = frozenset(
    {
        "font/ttf",
        "application/x-font-ttf",
        "application/x-font-truetype",
        "application/octet-stream",
        "application/font-sfnt",
        "",
    }
)

_CT_EXT: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "font/ttf": ".ttf",
    "application/octet-stream": ".ttf",
    "application/x-font-ttf": ".ttf",
    "application/x-font-truetype": ".ttf",
    "application/font-sfnt": ".ttf",
}


def s3_assets_configured(app_settings: Settings) -> bool:
    return bool(
        app_settings.aws_access_key_id
        and app_settings.aws_secret_access_key
        and app_settings.aws_region
        and app_settings.s3_bucket_name
        and app_settings.public_s3_base_url
    )


def build_s3_public_url(app_settings: Settings, key: str) -> str:
    base = (app_settings.public_s3_base_url or "").rstrip("/")
    k = key.lstrip("/")
    return f"{base}/{k}"


def _s3_client(app_settings: Settings):
    import boto3

    return boto3.client(
        "s3",
        region_name=app_settings.aws_region,
        aws_access_key_id=app_settings.aws_access_key_id,
        aws_secret_access_key=app_settings.aws_secret_access_key,
        config=Config(signature_version="s3v4"),
    )


def delete_s3_object(app_settings: Settings, key: str | None) -> None:
    if not key or not s3_assets_configured(app_settings):
        return
    client = _s3_client(app_settings)
    client.delete_object(Bucket=app_settings.s3_bucket_name, Key=key)


def presign_settings_asset_put(
    app_settings: Settings,
    *,
    company_id: int,
    kind: SettingsAssetKind,
    content_type: str,
) -> dict[str, Any]:
    raw_ct = (content_type or "").split(";")[0].strip()
    ct_lower = raw_ct.lower()
    if kind == "quali_font":
        if ct_lower not in _FONT_CT:
            raise ValueError("Unsupported Content-Type for font upload")
        ext = _CT_EXT.get(ct_lower, ".ttf")
    else:
        if ct_lower not in _IMAGE_CT:
            raise ValueError("Unsupported Content-Type for image upload")
        ext = _CT_EXT.get(ct_lower, ".bin")

    key = f"company/{company_id}/{_KIND_PREFIX[kind]}-{uuid.uuid4().hex}{ext}"
    client = _s3_client(app_settings)
    bucket = app_settings.s3_bucket_name
    if not bucket:
        raise RuntimeError("S3 bucket not configured")

    ct_for_sign = raw_ct or "application/octet-stream"
    url = client.generate_presigned_url(
        ClientMethod="put_object",
        Params={"Bucket": bucket, "Key": key, "ContentType": ct_for_sign},
        ExpiresIn=3600,
        HttpMethod="PUT",
    )
    public_url = build_s3_public_url(app_settings, key)
    return {
        "upload_url": url,
        "storage_key": key,
        "public_url": public_url,
        "headers": {"Content-Type": ct_for_sign},
    }


def is_company_scoped_storage_key(company_id: int, key: str) -> bool:
    k = key.strip().lstrip("/")
    prefix = f"company/{company_id}/"
    return k.startswith(prefix) and ".." not in k


def normalize_storage_key(company_id: int, key: str) -> str:
    k = key.strip().lstrip("/")
    if not is_company_scoped_storage_key(company_id, k):
        raise ValueError("Invalid storage key for this company")
    return k


def is_stored_s3_key(app_settings: Settings, company_id: int, path: str | None) -> bool:
    if not path or path.startswith("http://") or path.startswith("https://"):
        return False
    return bool(s3_assets_configured(app_settings)) and is_company_scoped_storage_key(company_id, path)
