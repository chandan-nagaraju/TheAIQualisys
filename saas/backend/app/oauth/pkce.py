"""PKCE S256 helpers (RFC 7636)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets

_VERIFIER_RE = re.compile(r"^[A-Za-z0-9\-._~]{43,128}$")
_CHALLENGE_RE = re.compile(r"^[A-Za-z0-9\-_]{43,128}$")


def generate_code_verifier() -> str:
    return secrets.token_urlsafe(64)[:96]


def challenge_s256(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def validate_code_verifier(code_verifier: str) -> bool:
    return bool(code_verifier) and bool(_VERIFIER_RE.match(code_verifier))


def validate_code_challenge(code_challenge: str) -> bool:
    return bool(code_challenge) and bool(_CHALLENGE_RE.match(code_challenge))


def verify_pkce_s256(*, code_verifier: str, code_challenge: str) -> bool:
    if not validate_code_verifier(code_verifier):
        return False
    if not validate_code_challenge(code_challenge):
        return False
    return hmac.compare_digest(challenge_s256(code_verifier), code_challenge)


def hash_secret(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_authorization_code() -> str:
    return secrets.token_urlsafe(32)


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)
