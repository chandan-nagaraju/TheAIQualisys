"""OAuth error types and JSON responses (RFC 6749). Never include tokens."""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import status
from fastapi.responses import JSONResponse, RedirectResponse


class OAuthError(Exception):
    def __init__(
        self,
        error: str,
        *,
        description: str | None = None,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.error = error
        self.description = description
        self.status_code = status_code
        self.headers = headers or {}
        super().__init__(error)


def oauth_error_response(exc: OAuthError) -> JSONResponse:
    body: dict[str, str] = {"error": exc.error}
    if exc.description:
        body["error_description"] = exc.description
    return JSONResponse(status_code=exc.status_code, content=body, headers=exc.headers)


def redirect_with_oauth_error(
    redirect_uri: str,
    *,
    error: str,
    state: str | None,
    description: str | None = None,
) -> RedirectResponse:
    params: dict[str, str] = {"error": error}
    if description:
        params["error_description"] = description
    if state:
        params["state"] = state
    sep = "&" if "?" in redirect_uri else "?"
    return RedirectResponse(url=f"{redirect_uri}{sep}{urlencode(params)}", status_code=302)
