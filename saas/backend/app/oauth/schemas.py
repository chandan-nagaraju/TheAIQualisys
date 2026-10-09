"""Request/response schemas for desktop OAuth."""

from __future__ import annotations

from pydantic import BaseModel, Field


class OAuthConsentRequest(BaseModel):
    client_id: str = Field(min_length=1, max_length=64)
    redirect_uri: str = Field(min_length=1, max_length=2048)
    scope: str = Field(min_length=1, max_length=255)
    state: str = Field(min_length=1, max_length=255)
    code_challenge: str = Field(min_length=43, max_length=128)
    code_challenge_method: str = Field(default="S256")
    decision: str = Field(description="approve | deny")


class OAuthConsentResponse(BaseModel):
    redirect_to: str


class OAuthAuthorizePreview(BaseModel):
    client_id: str
    client_name: str
    redirect_uri: str
    scope: str
    state: str
    code_challenge_method: str


class OAuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    refresh_token: str
    scope: str


class OAuthRevokeRequest(BaseModel):
    token: str | None = None
    client_id: str = Field(min_length=1, max_length=64)
    revoke_all: bool = False


class OAuthRevokeResponse(BaseModel):
    ok: bool = True
    revoked: int = 0
