"""Secure license-key generation and storage helpers.

Rules:
- License keys are generated server-side only.
- Plaintext keys are returned to the customer at mint time (email / reveal) and
  must not be stored as the sole durable representation.
- Durable storage uses SHA-256 hex of the plaintext key (lookup) plus an
  optional Fernet ciphertext when LICENSE_KEY_ENCRYPTION_SECRET is configured.
- Production Ed25519 signing private keys must NEVER live in this module's
  source, desktop apps, or git. They are loaded from environment / secret store
  in later phases (Phase 7).
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


def _fernet_from_secret(secret: str) -> Fernet:
    """Derive a Fernet key from an arbitrary secret string.

    Accepts either a valid Fernet url-safe-base64 key, or any passphrase which
    is stretched via SHA-256 to 32 bytes then urlsafe-b64-encoded.
    """
    secret = (secret or "").strip()
    if not secret:
        raise ValueError("encryption secret is empty")
    try:
        return Fernet(secret.encode("utf-8") if isinstance(secret, str) else secret)
    except Exception:
        digest = hashlib.sha256(secret.encode("utf-8")).digest()
        import base64

        return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_license_key(plaintext: str, secret: Optional[str]) -> Optional[str]:
    """Encrypt plaintext for reversible admin/customer reveal. Returns None if no secret."""
    if not secret:
        return None
    f = _fernet_from_secret(secret)
    return f.encrypt(normalize_license_key(plaintext).encode("utf-8")).decode("utf-8")


def decrypt_license_key(ciphertext: str, secret: Optional[str]) -> Optional[str]:
    """Decrypt a stored ciphertext. Returns None if secret missing or token invalid."""
    if not secret or not ciphertext:
        return None
    try:
        f = _fernet_from_secret(secret)
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
