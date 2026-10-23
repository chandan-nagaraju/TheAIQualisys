"""Secure license-key generation and storage helpers.

Rules:
- License keys are generated server-side only.
- Plaintext is returned once at mint time (email / reveal) and must not be the
  sole durable representation.
- Durable storage: SHA-256 hex for lookup + Fernet ciphertext for authorized reveal.
- LICENSE_KEY_ENCRYPTION_SECRET must be a valid Fernet key (url-safe base64, 32 raw bytes).
  Passphrase→SHA-256 derivation is intentionally NOT supported (too weak).
- Production Ed25519 signing private keys must NEVER live here or in desktop apps.
"""

from __future__ import annotations

import hashlib
import secrets
import string
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken


_KEY_ALPHABET = string.ascii_uppercase + string.digits
# Exclude ambiguous characters for human transcription.
_KEY_ALPHABET = "".join(c for c in _KEY_ALPHABET if c not in "01OI")


class LicenseKeyEncryptionError(ValueError):
    """Raised when LICENSE_KEY_ENCRYPTION_SECRET is missing or not a valid Fernet key."""


def generate_license_key(*, prefix: str = "AQ", groups: int = 4, group_len: int = 4) -> str:
    """Return a new human-readable license key, e.g. AQ-XXXX-XXXX-XXXX-XXXX."""
    parts = [prefix.upper()]
    for _ in range(groups):
        parts.append("".join(secrets.choice(_KEY_ALPHABET) for _ in range(group_len)))
    return "-".join(parts)


def normalize_license_key(raw: str) -> str:
    """Normalize user-entered keys for hashing / comparison."""
    return "".join(ch for ch in (raw or "").strip().upper() if ch.isalnum() or ch == "-")


def hash_license_key(plaintext: str) -> str:
    """SHA-256 hex digest of the normalized plaintext key (lookup key)."""
    normalized = normalize_license_key(plaintext)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def fernet_from_secret(secret: Optional[str]) -> Fernet:
    """
    Build a Fernet instance from LICENSE_KEY_ENCRYPTION_SECRET.

    The secret MUST already be a valid Fernet key (output of Fernet.generate_key()).
    Weak passphrase stretching is rejected fail-closed.
    """
    if secret is None or not str(secret).strip():
        raise LicenseKeyEncryptionError(
            "LICENSE_KEY_ENCRYPTION_SECRET is required and must be a valid Fernet key "
            "(url-safe base64-encoded 32-byte key). Generate with: "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\" "
            "— do this in a secure environment; never commit the production value."
        )
    raw = str(secret).strip().encode("utf-8")
    try:
        return Fernet(raw)
    except Exception as exc:
        raise LicenseKeyEncryptionError(
            "LICENSE_KEY_ENCRYPTION_SECRET is not a valid Fernet key. "
            "Do not use a passphrase; use Fernet.generate_key() output only."
        ) from exc


def require_valid_encryption_secret(secret: Optional[str]) -> str:
    """Validate and return the stripped Fernet key string; raise LicenseKeyEncryptionError otherwise."""
    fernet_from_secret(secret)
    return str(secret).strip()


def encrypt_license_key(plaintext: str, secret: Optional[str]) -> str:
    """Encrypt plaintext for reversible admin/customer reveal. Fail-closed if secret invalid."""
    f = fernet_from_secret(secret)
    return f.encrypt(normalize_license_key(plaintext).encode("utf-8")).decode("utf-8")


def decrypt_license_key(ciphertext: str, secret: Optional[str]) -> Optional[str]:
    """Decrypt a stored ciphertext. Returns None if token invalid; raises if secret invalid/missing."""
    if not ciphertext:
        return None
    f = fernet_from_secret(secret)
    try:
        return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError):
        return None


def mask_license_key(plaintext: str) -> str:
    """Mask a key for default UI display: show prefix + last group."""
    normalized = normalize_license_key(plaintext)
    parts = normalized.split("-")
    if len(parts) < 2:
        if len(normalized) <= 4:
            return "****"
        return f"{normalized[:2]}****{normalized[-4:]}"
    return f"{parts[0]}-****-****-****-{parts[-1]}"


def verify_license_key(plaintext: str, key_hash: str) -> bool:
    """Constant-time-ish compare of hash(plaintext) to stored hash."""
    candidate = hash_license_key(plaintext)
    return secrets.compare_digest(candidate, (key_hash or "").strip().lower())
