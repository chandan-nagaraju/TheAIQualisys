"""Phase 6: installer admin management + protected customer downloads."""

from __future__ import annotations

import hashlib
import secrets
from datetime import date, datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException, UploadFile
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import Settings
from app.licensing.constants import (
    DOWNLOAD_TOKEN_BYTES,
    ENTITLEMENT_PAID,
    ENTITLEMENT_TRIAL,
    INSTALLER_ALLOWED_CONTENT_TYPES,
    INSTALLER_ALLOWED_EXTENSIONS,
    INSTALLER_CHANNEL_ARCHIVED,
    INSTALLER_CHANNEL_CURRENT,
    INSTALLER_CHANNEL_MANDATORY,
    INSTALLER_CHANNEL_RECOMMENDED,
    LICENSE_STATUS_ACTIVE,
    LICENSE_STATUS_ISSUED,
)
from app.licensing.installer_storage import (
    build_installer_storage_key,
    private_installer_storage_configured,
    put_installer_bytes,
    presign_installer_get,
    sanitize_installer_filename,
)
from app.licensing.models import (
    DesktopDownloadToken,
    DesktopInstaller,
    DesktopLicense,
    DesktopProduct,
)
from app.licensing.service import get_product_or_404, record_license_event
from app.models import CompanyUser, PlatformAdmin

_VALID_CHANNELS = frozenset(
    {
        INSTALLER_CHANNEL_CURRENT,
        INSTALLER_CHANNEL_RECOMMENDED,
        INSTALLER_CHANNEL_MANDATORY,
        INSTALLER_CHANNEL_ARCHIVED,
    }
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def hash_download_token(raw: str) -> str:
    return hashlib.sha256((raw or "").encode("utf-8")).hexdigest()


def serialize_installer_admin(row: DesktopInstaller, *, product: Optional[DesktopProduct] = None) -> dict[str, Any]:
    """Admin metadata — includes storage_key for ops, never AWS credentials or public URLs."""
    out: dict[str, Any] = {
        "id": row.id,
        "product_id": row.product_id,
        "version": row.version,
        "release_channel": row.release_channel,
        "listing_active": bool(row.listing_active),
        "min_supported_version": row.min_supported_version,
        "min_windows_version": row.min_windows_version,
        "file_name": row.file_name,
        "file_sha256": row.file_sha256,
        "file_size_bytes": row.file_size_bytes,
        "release_date": row.release_date.isoformat() if row.release_date else None,
        "release_notes": row.release_notes,
        "has_file": bool(row.storage_key and row.file_sha256),
        "storage_key": row.storage_key,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
    if product is not None:
        out["product_code"] = product.code
        out["product_name"] = product.name
    return out


def serialize_installer_customer(row: DesktopInstaller, *, product: DesktopProduct) -> dict[str, Any]:
    """Customer-safe installer card — no storage_key / URLs / credentials."""
    return {
        "id": row.id,
        "product_id": row.product_id,
        "product_code": product.code,
        "product_name": product.name,
        "version": row.version,
        "release_channel": row.release_channel,
        "is_current": row.release_channel == INSTALLER_CHANNEL_CURRENT,
        "is_recommended": row.release_channel == INSTALLER_CHANNEL_RECOMMENDED,
        "is_mandatory": row.release_channel == INSTALLER_CHANNEL_MANDATORY,
        "min_windows_version": row.min_windows_version,
        "file_name": row.file_name,
        "file_sha256": row.file_sha256,
        "file_size_bytes": row.file_size_bytes,
        "release_date": row.release_date.isoformat() if row.release_date else None,
        "release_notes": row.release_notes,
    }


def license_entitles_download(lic: DesktopLicense, *, now: Optional[datetime] = None) -> bool:
    """Paid or trial + issued/active + wall-clock expiry. No device binding required."""
    if int(lic.licensed_user_id) <= 0:
        return False
    ent = (lic.entitlement_type or "").lower()
    if ent not in (ENTITLEMENT_PAID, ENTITLEMENT_TRIAL):
        return False
    status = (lic.status or "").lower()
    if status not in (LICENSE_STATUS_ISSUED, LICENSE_STATUS_ACTIVE):
        return False
    when = now or _utc_now()
    if lic.expires_at is not None:
        exp = lic.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp <= when:
            return False
    return True


def find_entitling_license(
    db: Session, *, user: CompanyUser, product_id: int
) -> Optional[DesktopLicense]:
    rows = db.execute(
        select(DesktopLicense).where(
            DesktopLicense.licensed_user_id == int(user.id),
            DesktopLicense.product_id == int(product_id),
        )
    ).scalars().all()
    now = _utc_now()
    for lic in rows:
        # Defense in depth: never trust a row for another user even if query is mocked/bypassed
        if int(lic.licensed_user_id) != int(user.id):
            continue
        if int(lic.product_id) != int(product_id):
            continue
        if license_entitles_download(lic, now=now):
            return lic
    return None


def entitled_product_ids(db: Session, *, user: CompanyUser) -> set[int]:
    rows = db.execute(
        select(DesktopLicense).where(DesktopLicense.licensed_user_id == int(user.id))
    ).scalars().all()
    now = _utc_now()
    return {int(lic.product_id) for lic in rows if license_entitles_download(lic, now=now)}


def installer_customer_eligible(row: DesktopInstaller) -> bool:
    if not bool(row.listing_active):
        return False
    channel = (row.release_channel or "").lower()
    if channel == INSTALLER_CHANNEL_ARCHIVED:
        return False
    if not row.storage_key or not row.file_sha256 or not row.file_size_bytes:
        return False
    return True


def list_installers_admin(db: Session, *, product_id: int) -> list[DesktopInstaller]:
    return list(
        db.execute(
            select(DesktopInstaller)
            .where(DesktopInstaller.product_id == int(product_id))
            .order_by(DesktopInstaller.id.desc())
        ).scalars().all()
    )


def create_installer_version(
    db: Session,
    *,
    admin: PlatformAdmin,
    product_id: int,
    version: str,
    release_notes: Optional[str] = None,
    release_date: Optional[date] = None,
    min_windows_version: Optional[str] = None,
    min_supported_version: Optional[str] = None,
) -> DesktopInstaller:
    product = get_product_or_404(db, product_id)
    ver = (version or "").strip()
    if not ver or len(ver) > 64:
        raise HTTPException(status_code=400, detail="Invalid version")
    existing = db.execute(
        select(DesktopInstaller).where(
            DesktopInstaller.product_id == product.id,
            DesktopInstaller.version == ver,
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Version already exists for this product")
    row = DesktopInstaller(
        product_id=product.id,
        version=ver,
        release_channel=INSTALLER_CHANNEL_RECOMMENDED,
        listing_active=0,
        release_notes=(release_notes or "").strip() or None,
        release_date=release_date,
        min_windows_version=(min_windows_version or "").strip() or None,
        min_supported_version=(min_supported_version or "").strip() or None,
    )
    db.add(row)
    db.flush()
    record_license_event(
        db,
        license_id=None,
        actor_type="admin",
        actor_id=admin.id,
        event_type="installer_created",
        meta={"installer_id": row.id, "product_id": product.id, "version": ver},
    )
    return row


async def upload_installer_file(
    db: Session,
    settings: Settings,
    *,
    admin: PlatformAdmin,
    installer_id: int,
    file: UploadFile,
) -> DesktopInstaller:
    row = db.get(DesktopInstaller, int(installer_id))
    if not row:
        raise HTTPException(status_code=404, detail="Installer not found")
    product = get_product_or_404(db, row.product_id)
    if not private_installer_storage_configured(settings):
        raise HTTPException(status_code=503, detail="Private installer storage is not configured")

    raw_name = file.filename or "installer.exe"
    try:
        safe_name = sanitize_installer_filename(raw_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    mime = (file.content_type or "application/octet-stream").lower().split(";")[0].strip()
    if mime and mime not in INSTALLER_ALLOWED_CONTENT_TYPES:
        # Allow octet-stream always; reject clearly wrong types
        if mime.startswith("text/") or mime.startswith("image/"):
            raise HTTPException(status_code=400, detail="Unsupported installer content type")

    data = await file.read()
    max_bytes = int(settings.installer_max_upload_bytes or 0) or (512 * 1024 * 1024)
    if not data:
        raise HTTPException(status_code=400, detail="Empty installer upload")
    if len(data) > max_bytes:
        raise HTTPException(status_code=400, detail="Installer exceeds maximum upload size")

    try:
        key = build_installer_storage_key(
            product_code=product.code, version=row.version, safe_filename=safe_name
        )
        put = put_installer_bytes(settings, storage_key=key, data=data, content_type=mime or "application/octet-stream")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    row.storage_key = put.storage_key
    row.storage_url = None  # never permanent public URL
    row.file_name = safe_name
    row.file_sha256 = put.file_sha256
    row.file_size_bytes = put.file_size_bytes
    db.add(row)
    record_license_event(
        db,
        license_id=None,
        actor_type="admin",
        actor_id=admin.id,
        event_type="installer_uploaded",
        meta={
            "installer_id": row.id,
            "product_id": product.id,
            "version": row.version,
            "file_sha256": put.file_sha256,
            "file_size_bytes": put.file_size_bytes,
            # never log credentials or permanent URLs
        },
    )
    db.flush()
    return row


def patch_installer(
    db: Session,
    *,
    admin: PlatformAdmin,
    installer_id: int,
    release_notes: Optional[str] = None,
    release_date: Optional[date] = None,
    min_windows_version: Optional[str] = None,
    min_supported_version: Optional[str] = None,
    clear_notes: bool = False,
) -> DesktopInstaller:
    row = db.get(DesktopInstaller, int(installer_id))
    if not row:
        raise HTTPException(status_code=404, detail="Installer not found")
    if release_notes is not None:
        row.release_notes = release_notes.strip() or None
    if clear_notes:
        row.release_notes = None
    if release_date is not None:
        row.release_date = release_date
    if min_windows_version is not None:
        row.min_windows_version = min_windows_version.strip() or None
    if min_supported_version is not None:
        row.min_supported_version = min_supported_version.strip() or None
    db.add(row)
    record_license_event(
        db,
        license_id=None,
        actor_type="admin",
        actor_id=admin.id,
        event_type="installer_metadata_updated",
        meta={"installer_id": row.id},
    )
    db.flush()
    return row


def set_installer_listing(
    db: Session,
    *,
    admin: PlatformAdmin,
    installer_id: int,
    listing_active: bool,
) -> DesktopInstaller:
    row = db.get(DesktopInstaller, int(installer_id))
    if not row:
        raise HTTPException(status_code=404, detail="Installer not found")
    if listing_active and not (row.storage_key and row.file_sha256):
        raise HTTPException(status_code=400, detail="Upload installer file before publishing")
    if listing_active and (row.release_channel or "").lower() == INSTALLER_CHANNEL_ARCHIVED:
        raise HTTPException(status_code=400, detail="Archived installers cannot be published; change channel first")
    row.listing_active = 1 if listing_active else 0
    db.add(row)
    record_license_event(
        db,
        license_id=None,
        actor_type="admin",
        actor_id=admin.id,
        event_type="installer_published" if listing_active else "installer_unpublished",
        meta={"installer_id": row.id},
    )
    db.flush()
    return row


def set_installer_channel(
    db: Session,
    *,
    admin: PlatformAdmin,
    installer_id: int,
    channel: str,
) -> DesktopInstaller:
    ch = (channel or "").strip().lower()
    if ch not in _VALID_CHANNELS:
        raise HTTPException(status_code=400, detail="Invalid release channel")
    row = db.get(DesktopInstaller, int(installer_id))
    if not row:
        raise HTTPException(status_code=404, detail="Installer not found")

    # Exclusive channels: demote any existing peer with the same channel on this product.
    if ch in (INSTALLER_CHANNEL_CURRENT, INSTALLER_CHANNEL_RECOMMENDED, INSTALLER_CHANNEL_MANDATORY):
        peers = db.execute(
            select(DesktopInstaller).where(
                DesktopInstaller.product_id == row.product_id,
                DesktopInstaller.id != row.id,
                DesktopInstaller.release_channel == ch,
            )
        ).scalars().all()
        for peer in peers:
            if ch == INSTALLER_CHANNEL_CURRENT:
                peer.release_channel = INSTALLER_CHANNEL_RECOMMENDED
            elif ch == INSTALLER_CHANNEL_RECOMMENDED:
                peer.release_channel = INSTALLER_CHANNEL_MANDATORY
            else:
                peer.release_channel = INSTALLER_CHANNEL_RECOMMENDED
            db.add(peer)

    row.release_channel = ch
    if ch == INSTALLER_CHANNEL_ARCHIVED:
        row.listing_active = 0
    db.add(row)
    event = "installer_archived" if ch == INSTALLER_CHANNEL_ARCHIVED else "installer_channel_set"
    record_license_event(
        db,
        license_id=None,
        actor_type="admin",
        actor_id=admin.id,
        event_type=event,
        meta={"installer_id": row.id, "release_channel": ch},
    )
    db.flush()
    return row


def list_customer_downloads(db: Session, *, user: CompanyUser) -> list[dict[str, Any]]:
    ids = entitled_product_ids(db, user=user)
    if not ids:
        return []
    products = db.execute(select(DesktopProduct).where(DesktopProduct.id.in_(ids))).scalars().all()
    out: list[dict[str, Any]] = []
    for product in sorted(products, key=lambda p: p.sort_order):
        installers = [
            i
            for i in list_installers_admin(db, product_id=product.id)
            if installer_customer_eligible(i)
        ]
        if not installers:
            out.append(
                {
                    "product_id": product.id,
                    "product_code": product.code,
                    "product_name": product.name,
                    "current": None,
                    "recommended": None,
                    "versions": [],
                }
            )
            continue
        current = next((i for i in installers if i.release_channel == INSTALLER_CHANNEL_CURRENT), None)
        recommended = next(
            (i for i in installers if i.release_channel == INSTALLER_CHANNEL_RECOMMENDED), current
        )
        out.append(
            {
                "product_id": product.id,
                "product_code": product.code,
                "product_name": product.name,
                "current": serialize_installer_customer(current, product=product) if current else None,
                "recommended": serialize_installer_customer(recommended, product=product)
                if recommended
                else None,
                "versions": [serialize_installer_customer(i, product=product) for i in installers],
            }
        )
    return out


def list_customer_product_versions(db: Session, *, user: CompanyUser, product_code: str) -> dict[str, Any]:
    code = (product_code or "").strip().upper()
    product = db.execute(select(DesktopProduct).where(DesktopProduct.code == code)).scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if not find_entitling_license(db, user=user, product_id=product.id):
        raise HTTPException(status_code=404, detail="Product not found")
    rows = list_customer_downloads(db, user=user)
    for item in rows:
        if item["product_id"] == product.id:
            return item
    return {
        "product_id": product.id,
        "product_code": product.code,
        "product_name": product.name,
        "current": None,
        "recommended": None,
        "versions": [],
    }


def mint_download_token(
    db: Session,
    settings: Settings,
    *,
    user: CompanyUser,
    installer_id: int,
) -> tuple[str, DesktopDownloadToken]:
    row = db.get(DesktopInstaller, int(installer_id))
    if not row or not installer_customer_eligible(row):
        raise HTTPException(status_code=404, detail="Installer not found")
    lic = find_entitling_license(db, user=user, product_id=row.product_id)
    if not lic:
        raise HTTPException(status_code=403, detail="Not entitled to download this product")

    raw = secrets.token_urlsafe(DOWNLOAD_TOKEN_BYTES)
    token_hash = hash_download_token(raw)
    ttl = int(settings.installer_download_token_ttl_seconds or 120)
    ttl = max(60, min(ttl, 300))
    from datetime import timedelta

    token = DesktopDownloadToken(
        token_hash=token_hash,
        user_id=int(user.id),
        installer_id=int(row.id),
        license_id=int(lic.id),
        expires_at=_utc_now() + timedelta(seconds=ttl),
    )
    db.add(token)
    db.flush()
    record_license_event(
        db,
        license_id=lic.id,
        actor_type="user",
        actor_id=user.id,
        event_type="download_token_minted",
        meta={"installer_id": row.id, "token_id": token.id, "ttl_seconds": ttl},
    )
    return raw, token


def redeem_download_token(
    db: Session,
    settings: Settings,
    *,
    user: CompanyUser,
    raw_token: str,
) -> dict[str, Any]:
    """Atomically redeem single-use token and return short-lived private GET URL."""
    th = hash_download_token(raw_token)
    tok = db.execute(
        select(DesktopDownloadToken).where(DesktopDownloadToken.token_hash == th).with_for_update()
    ).scalar_one_or_none()
    if not tok:
        raise HTTPException(status_code=404, detail="Download token not found")
    if int(tok.user_id) != int(user.id):
        raise HTTPException(status_code=404, detail="Download token not found")
    now = _utc_now()
    exp = tok.expires_at
    if exp is not None and exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp is not None and exp <= now:
        raise HTTPException(status_code=410, detail="Download token expired")
    if tok.used_at is not None:
        raise HTTPException(status_code=409, detail="Download token already used")

    installer = db.get(DesktopInstaller, int(tok.installer_id))
    if not installer or not installer_customer_eligible(installer):
        raise HTTPException(status_code=403, detail="Installer is no longer available")

    # Re-check entitlement at redeem time
    lic = None
    if tok.license_id:
        lic = db.get(DesktopLicense, int(tok.license_id))
    if lic is None or int(lic.licensed_user_id) != int(user.id):
        lic = find_entitling_license(db, user=user, product_id=installer.product_id)
    if lic is None or not license_entitles_download(lic, now=now):
        raise HTTPException(status_code=403, detail="License no longer entitles download")
    if int(lic.product_id) != int(installer.product_id):
        raise HTTPException(status_code=403, detail="License product mismatch")

    # Atomic single-use: only succeed if used_at still null
    result = db.execute(
        update(DesktopDownloadToken)
        .where(
            DesktopDownloadToken.id == tok.id,
            DesktopDownloadToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
    if result.rowcount != 1:
        raise HTTPException(status_code=409, detail="Download token already used")

    if not installer.storage_key:
        raise HTTPException(status_code=503, detail="Installer file missing")
    if not private_installer_storage_configured(settings):
        raise HTTPException(status_code=503, detail="Private installer storage is not configured")

    try:
        url = presign_installer_get(
            settings, storage_key=installer.storage_key, file_name=installer.file_name
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not create download URL") from exc

    record_license_event(
        db,
        license_id=lic.id,
        actor_type="user",
        actor_id=user.id,
        event_type="download_redeemed",
        meta={"installer_id": installer.id, "token_id": tok.id},
    )
    db.flush()
    # Short-lived URL only — never permanent, never credentials
    return {
        "download_url": url,
        "expires_in_seconds": int(settings.installer_presign_get_ttl_seconds or 60),
        "file_name": installer.file_name,
        "file_sha256": installer.file_sha256,
        "file_size_bytes": installer.file_size_bytes,
    }
