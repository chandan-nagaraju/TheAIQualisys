"""Feature-flag helpers for desktop licensing."""

from __future__ import annotations

from fastapi import HTTPException, status

from app.config import get_settings


def is_desktop_licensing_enabled() -> bool:
    return bool(get_settings().enable_desktop_licensing)


def require_desktop_licensing_enabled() -> None:
    """Raise 404 when the feature is disabled so routes appear absent in production."""
    if not is_desktop_licensing_enabled():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found",
        )
