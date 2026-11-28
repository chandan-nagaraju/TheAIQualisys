import pytest
from pydantic import ValidationError

from app.schemas import PlatformAdminCreateBody, PlatformAdminSetPasswordBody


def test_create_admin_requires_matching_passwords() -> None:
    with pytest.raises(ValidationError):
        PlatformAdminCreateBody(
            email="admin@theaiqualisys.com",
            password="longenough",
            confirm_password="different1",
        )
    body = PlatformAdminCreateBody(
        email="admin@theaiqualisys.com",
        password="longenough",
        confirm_password="longenough",
    )
    assert "theaiqualisys.com" in str(body.email)


def test_set_admin_password_requires_match() -> None:
    with pytest.raises(ValidationError):
        PlatformAdminSetPasswordBody(password="longenough", confirm_password="nope1234")
    PlatformAdminSetPasswordBody(password="longenough", confirm_password="longenough")
