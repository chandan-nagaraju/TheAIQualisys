"""Private installer object storage (Phase 6).

Never uses PUBLIC_S3_BASE_URL. Production: private S3. Tests: memory backend.
Customers never receive permanent URLs or AWS credentials.
"""

from __future__ import annotations

import hashlib
import re
import threading
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote

from botocore.config import Config

from app.config import Settings
from app.licensing.constants import INSTALLER_ALLOWED_EXTENSIONS

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
_MEMORY_LOCK = threading.Lock()
_MEMORY_OBJECTS: dict[str, bytes] = {}
_MEMORY_META: dict[str, dict] = {}


@dataclass
class PutResult:
    storage_key: str
    file_sha256: str
    file_size_bytes: int
    content_type: str


def private_installer_storage_configured(settings: Settings) -> bool:
    backend = (settings.installer_storage_backend or "s3").strip().lower()
    if backend == "memory":
        return True
    return bool(
        settings.aws_access_key_id
        and settings.aws_secret_access_key
        and settings.aws_region
        and installer_bucket(settings)
    )


def installer_bucket(settings: Settings) -> Optional[str]:
    return (settings.installer_s3_bucket or settings.s3_bucket_name or "").strip() or None


def sanitize_installer_filename(raw: str) -> str:
    original = raw or ""
    if ".." in original or original.startswith("/") or ":\\" in original or ":/" in original[:3]:
        raise ValueError("Path traversal rejected")
    if "\\" in original or "/" in original:
        # Only basename allowed — reject if caller passed a path
        raise ValueError("Path traversal rejected")
    name = original.strip().lstrip(".")
    name = _SAFE_NAME_RE.sub("_", name)
    if not name or name in {".", ".."}:
        raise ValueError("Invalid installer filename")
    if ".." in name or "/" in name or "\\" in name:
        raise ValueError("Path traversal rejected")
    lower = name.lower()
    if not any(lower.endswith(ext) for ext in INSTALLER_ALLOWED_EXTENSIONS):
        raise ValueError("Unsupported installer file type")
    if len(name) > 200:
        name = name[:200]
    return name


def build_installer_storage_key(*, product_code: str, version: str, safe_filename: str) -> str:
    """Server-only key construction. Never accept client-supplied keys."""
    raw_code = product_code or ""
    raw_ver = version or ""
    if ".." in raw_code or ".." in raw_ver or "/" in raw_code or "\\" in raw_code:
        raise ValueError("Invalid product/version for storage key")
    code = re.sub(r"[^A-Za-z0-9_-]+", "_", raw_code.strip().upper())
    ver = re.sub(r"[^A-Za-z0-9._-]+", "_", raw_ver.strip())
    fname = sanitize_installer_filename(safe_filename)
    if not code or not ver or code.startswith(".") or ver.startswith("."):
        raise ValueError("Invalid product/version for storage key")
    # Fixed prefix segment — no customer control
    return f"desktop-installers/{code}/{ver}/{fname}"


def _s3_client(settings: Settings):
    import boto3

    return boto3.client(
        "s3",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        config=Config(signature_version="s3v4"),
    )


def put_installer_bytes(
    settings: Settings,
    *,
    storage_key: str,
    data: bytes,
    content_type: str = "application/octet-stream",
) -> PutResult:
    if not storage_key.startswith("desktop-installers/"):
        raise ValueError("Invalid storage key prefix")
    if ".." in storage_key or storage_key.startswith("/"):
        raise ValueError("Invalid storage key")
    max_bytes = int(settings.installer_max_upload_bytes or 0) or (512 * 1024 * 1024)
    if len(data) > max_bytes:
        raise ValueError("Installer exceeds maximum upload size")
    if not data:
        raise ValueError("Empty installer upload")
    digest = hashlib.sha256(data).hexdigest()
    ct = (content_type or "application/octet-stream").split(";")[0].strip() or "application/octet-stream"
    backend = (settings.installer_storage_backend or "s3").strip().lower()
    if backend == "memory":
        with _MEMORY_LOCK:
            _MEMORY_OBJECTS[storage_key] = data
            _MEMORY_META[storage_key] = {"content_type": ct, "size": len(data), "sha256": digest}
        return PutResult(storage_key=storage_key, file_sha256=digest, file_size_bytes=len(data), content_type=ct)

    if not private_installer_storage_configured(settings):
        raise RuntimeError("Private installer storage is not configured")
    bucket = installer_bucket(settings)
    assert bucket
    client = _s3_client(settings)
    client.put_object(Bucket=bucket, Key=storage_key, Body=data, ContentType=ct)
    return PutResult(storage_key=storage_key, file_sha256=digest, file_size_bytes=len(data), content_type=ct)


def presign_installer_put(
    settings: Settings,
    *,
    storage_key: str,
    content_type: str = "application/octet-stream",
) -> str:
    if (settings.installer_storage_backend or "").strip().lower() == "memory":
        # Tests: return a placeholder; finalize uses memory put
        return f"memory://put/{quote(storage_key, safe='')}"
    if not private_installer_storage_configured(settings):
        raise RuntimeError("Private installer storage is not configured")
    if not storage_key.startswith("desktop-installers/"):
        raise ValueError("Invalid storage key prefix")
    bucket = installer_bucket(settings)
    assert bucket
    client = _s3_client(settings)
    return client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": bucket,
            "Key": storage_key,
            "ContentType": content_type or "application/octet-stream",
        },
        ExpiresIn=int(settings.installer_presign_put_ttl_seconds or 900),
    )


def presign_installer_get(settings: Settings, *, storage_key: str, file_name: Optional[str] = None) -> str:
    if (settings.installer_storage_backend or "").strip().lower() == "memory":
        return f"memory://get/{quote(storage_key, safe='')}"
    if not private_installer_storage_configured(settings):
        raise RuntimeError("Private installer storage is not configured")
    if not storage_key.startswith("desktop-installers/"):
        raise ValueError("Invalid storage key prefix")
    bucket = installer_bucket(settings)
    assert bucket
    client = _s3_client(settings)
    params: dict = {"Bucket": bucket, "Key": storage_key}
    if file_name:
        safe = sanitize_installer_filename(file_name)
        params["ResponseContentDisposition"] = f'attachment; filename="{safe}"'
    return client.generate_presigned_url(
        "get_object",
        Params=params,
        ExpiresIn=int(settings.installer_presign_get_ttl_seconds or 60),
    )


def fetch_installer_bytes(settings: Settings, *, storage_key: str) -> bytes:
    if (settings.installer_storage_backend or "").strip().lower() == "memory":
        with _MEMORY_LOCK:
            data = _MEMORY_OBJECTS.get(storage_key)
        if data is None:
            raise FileNotFoundError(storage_key)
        return data
    bucket = installer_bucket(settings)
    assert bucket
    client = _s3_client(settings)
    obj = client.get_object(Bucket=bucket, Key=storage_key)
    return obj["Body"].read()


def head_installer_object(settings: Settings, *, storage_key: str) -> dict:
    if (settings.installer_storage_backend or "").strip().lower() == "memory":
        with _MEMORY_LOCK:
            meta = _MEMORY_META.get(storage_key)
            data = _MEMORY_OBJECTS.get(storage_key)
        if not meta or data is None:
            raise FileNotFoundError(storage_key)
        return {"content_type": meta["content_type"], "size": meta["size"], "sha256": meta.get("sha256")}
    bucket = installer_bucket(settings)
    assert bucket
    client = _s3_client(settings)
    resp = client.head_object(Bucket=bucket, Key=storage_key)
    return {
        "content_type": (resp.get("ContentType") or "application/octet-stream").split(";")[0].strip(),
        "size": int(resp.get("ContentLength") or 0),
        "etag": (resp.get("ETag") or "").strip('"'),
    }


def clear_memory_store() -> None:
    with _MEMORY_LOCK:
        _MEMORY_OBJECTS.clear()
        _MEMORY_META.clear()
