from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt as _bcrypt
from jose import JWTError, jwt
from passlib.context import CryptContext
from werkzeug.security import check_password_hash as werkzeug_check_password_hash

from app.config import get_settings

# Passlib 1.7.x expects bcrypt.__about__.__version__, removed in newer bcrypt.
# Add a tiny compatibility shim so startup doesn't emit noisy tracebacks.
if not hasattr(_bcrypt, "__about__"):
    class _BcryptAbout:
        __version__ = getattr(_bcrypt, "__version__", "unknown")

    _bcrypt.__about__ = _BcryptAbout()  # type: ignore[attr-defined]

pwd_context = CryptContext(schemes=["bcrypt_sha256", "bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    # bcrypt_sha256 avoids bcrypt's 72-byte input limit while verify() still
    # accepts legacy bcrypt hashes already stored in the database.
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    if not hashed:
        return False
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
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
    try:
        ok, new_hash = pwd_context.verify_and_update(plain, hashed)
        if ok:
            return True, new_hash
    except Exception:
        pass
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
