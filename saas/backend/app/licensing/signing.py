"""Ed25519 signed offline entitlements (Phase 7).

Private key: LICENSE_SIGNING_PRIVATE_KEY (server-only). Never embed in desktop.
Desktop trust root must be a pinned public key in the signed app release — not
blind trust of GET /api/license/public-key.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from app.config import Settings
from app.licensing.constants import (
    ENTITLEMENT_PAID,
    LICENSE_ENTITLEMENT_ISSUER,
    LICENSE_ENTITLEMENT_SCHEMA_VERSION,
)

_PEM_BEGIN = "-----BEGIN"


class SigningKeyError(Exception):
    """Signing key missing or malformed — fail closed."""


@dataclass(frozen=True)
class SigningKeyMaterial:
    private_key: Ed25519PrivateKey
    public_key: Ed25519PublicKey
    public_key_pem: str
    kid: str


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + pad).encode("ascii"))


def kid_from_public_key_pem(pem: str) -> str:
    digest = hashlib.sha256(pem.strip().encode("utf-8")).hexdigest()
    return digest[:16]


def load_signing_key_material(settings: Settings) -> SigningKeyMaterial:
    raw = (settings.license_signing_private_key or "").strip()
    if not raw:
        raise SigningKeyError("LICENSE_SIGNING_PRIVATE_KEY is not configured")
    try:
        if _PEM_BEGIN in raw:
            private_key = serialization.load_pem_private_key(raw.encode("utf-8"), password=None)
            if not isinstance(private_key, Ed25519PrivateKey):
                raise SigningKeyError("LICENSE_SIGNING_PRIVATE_KEY must be an Ed25519 private key")
        else:
            # Raw 32-byte seed, standard base64 or urlsafe base64
            try:
                seed = base64.b64decode(raw, validate=True)
            except Exception:
                seed = _b64url_decode(raw)
            if len(seed) != 32:
                raise SigningKeyError("Raw Ed25519 seed must be 32 bytes")
            private_key = Ed25519PrivateKey.from_private_bytes(seed)
    except SigningKeyError:
        raise
    except Exception as exc:
        raise SigningKeyError("LICENSE_SIGNING_PRIVATE_KEY is malformed") from exc

    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return SigningKeyMaterial(
        private_key=private_key,
        public_key=public_key,
        public_key_pem=public_pem,
        kid=kid_from_public_key_pem(public_pem),
    )


def generate_ephemeral_signing_pem() -> str:
    """Test/lab helper only — never use for production secrets."""
    key = Ed25519PrivateKey.generate()
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _dt_to_unix(dt: Optional[datetime]) -> Optional[int]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def build_entitlement_claims(
    *,
    product_code: str,
    license_id: int,
    activation_id: int,
    licensed_user_id: int,
    fingerprint_hash: str,
    entitlement_type: str = ENTITLEMENT_PAID,
    status: str = "active",
    expires_at: Optional[datetime],
    max_offline_days: int,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    when = now or datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    iat = when
    offline = timedelta(days=max(1, int(max_offline_days)))
    naf_dt = iat + offline
    if expires_at is not None:
        exp = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=timezone.utc)
        if exp < naf_dt:
            naf_dt = exp
    claims: dict[str, Any] = {
        "v": LICENSE_ENTITLEMENT_SCHEMA_VERSION,
        "iss": LICENSE_ENTITLEMENT_ISSUER,
        "aud": (product_code or "").strip().upper(),
        "jti": secrets.token_hex(16),
        "license_id": int(license_id),
        "activation_id": int(activation_id),
        "uid": int(licensed_user_id),
        "fp": (fingerprint_hash or "").strip().lower(),
        "ent": (entitlement_type or ENTITLEMENT_PAID).lower(),
        "iat": _dt_to_unix(iat),
        "nbf": _dt_to_unix(iat),
        "naf": _dt_to_unix(naf_dt),
        "st": (status or "active").lower(),
    }
    if expires_at is not None:
        claims["exp"] = _dt_to_unix(expires_at)
    return claims


def sign_entitlement(settings: Settings, claims: dict[str, Any]) -> str:
    material = load_signing_key_material(settings)
    payload = canonical_json_bytes(claims)
    sig = material.private_key.sign(payload)
    return f"{_b64url_encode(payload)}.{_b64url_encode(sig)}"


def verify_entitlement_token(
    token: str,
    *,
    public_key_pem: str,
    expected_product: Optional[str] = None,
    expected_fp: Optional[str] = None,
    expected_license_id: Optional[int] = None,
    skew_seconds: int = 300,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Verify signature against an explicitly provided public key (pinned trust root)."""
    parts = (token or "").split(".")
    if len(parts) != 2:
        raise ValueError("Malformed entitlement token")
    payload_bytes = _b64url_decode(parts[0])
    sig = _b64url_decode(parts[1])
    public_key = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
    if not isinstance(public_key, Ed25519PublicKey):
        raise ValueError("Public key must be Ed25519")
    try:
        public_key.verify(sig, payload_bytes)
    except InvalidSignature as exc:
        raise ValueError("Invalid entitlement signature") from exc
    claims = json.loads(payload_bytes.decode("utf-8"))
    if not isinstance(claims, dict):
        raise ValueError("Invalid entitlement payload")
    if int(claims.get("v") or 0) != LICENSE_ENTITLEMENT_SCHEMA_VERSION:
        raise ValueError("Unsupported entitlement version")
    if claims.get("iss") != LICENSE_ENTITLEMENT_ISSUER:
        raise ValueError("Invalid entitlement issuer")
    if expected_product and (claims.get("aud") or "").upper() != expected_product.upper():
        raise ValueError("Product mismatch")
    if expected_fp and (claims.get("fp") or "").lower() != expected_fp.lower():
        raise ValueError("Device fingerprint mismatch")
    if expected_license_id is not None and int(claims.get("license_id") or 0) != int(expected_license_id):
        raise ValueError("License mismatch")

    when = now or datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    ts = int(when.timestamp())
    nbf = claims.get("nbf")
    if nbf is not None and ts + int(skew_seconds) < int(nbf):
        raise ValueError("Entitlement not yet valid")
    naf = claims.get("naf")
    if naf is not None and ts - int(skew_seconds) > int(naf):
        raise ValueError("Entitlement offline window expired")
    exp = claims.get("exp")
    if exp is not None and ts - int(skew_seconds) > int(exp):
        raise ValueError("Entitlement expired")
    return claims


def public_key_response(settings: Settings) -> dict[str, Any]:
    material = load_signing_key_material(settings)
    return {
        "algorithm": "Ed25519",
        "keys": [
            {
                "kid": material.kid,
                "public_key_pem": material.public_key_pem,
                "status": "current",
            }
        ],
        "trust_note": (
            "Desktop apps must embed/pin the production public key in the signed release. "
            "Do not treat this endpoint as the sole trust root."
        ),
    }


_FINGERPRINT_RE = re.compile(r"^[a-fA-F0-9]{64}$")


def validate_fingerprint_hash(value: str) -> str:
    fp = (value or "").strip().lower()
    if not _FINGERPRINT_RE.match(fp):
        raise ValueError("fingerprint_hash must be a 64-character SHA-256 hex digest")
    return fp
