from datetime import datetime, timedelta, timezone
import hashlib
from typing import Any

import bcrypt
from jose import JWTError, jwt
from werkzeug.security import check_password_hash as werkzeug_check_password_hash

from app.config import get_settings

def _sha256_ascii(password: str) -> bytes:
    # Pre-hash to fixed-length ASCII bytes so bcrypt never sees >72-byte input.
    return hashlib.sha256(password.encode("utf-8")).hexdigest().encode("ascii")


def _bcrypt_check(secret: bytes, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(secret, hashed.encode("utf-8"))
    except Exception:
        return False


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_sha256_ascii(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    if not hashed:
        return False
    # New hashes (bcrypt over SHA256(password))
    if _bcrypt_check(_sha256_ascii(plain), hashed):
        return True
    # Legacy bcrypt hashes (plain password, subject to old 72-byte truncation)
    if _bcrypt_check(plain.encode("utf-8"), hashed):
        return True
    # Legacy hashes from older stacks (e.g. Werkzeug pbkdf2/scrypt).
    try:
        return werkzeug_check_password_hash(hashed, plain)
    except Exception:
        return False


def verify_password_and_upgrade(plain: str, hashed: str) -> tuple[bool, str | None]:
    """
    Verify a password and return (ok, upgraded_hash).
    upgraded_hash is set when a legacy hash should be replaced.
    """
    if not hashed:
        return False, None
    # Already current scheme.
    if _bcrypt_check(_sha256_ascii(plain), hashed):
        return True, None
    # Legacy bcrypt hash: verify then upgrade.
    if _bcrypt_check(plain.encode("utf-8"), hashed):
        return True, hash_password(plain)
    # Legacy werkzeug hash: verify then upgrade.
    try:
        if werkzeug_check_password_hash(hashed, plain):
            return True, hash_password(plain)
    except Exception:
        pass
    return False, None


def create_access_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode: dict[str, Any] = {"sub": subject, "exp": expire, "typ": "company"}
    if extra:
        to_encode.update(extra)
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any] | None:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None


def create_admin_token(subject: str) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.admin_access_token_expire_minutes)
    to_encode = {"sub": subject, "exp": expire, "typ": "platform_admin"}
    return jwt.encode(to_encode, settings.admin_jwt_secret, algorithm=settings.jwt_algorithm)


def decode_admin_token(token: str) -> dict[str, Any] | None:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.admin_jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None
