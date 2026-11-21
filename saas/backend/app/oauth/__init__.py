"""Desktop OAuth 2.0 Authorization Code + PKCE (Phase 9C-B).

Independent of ENABLE_DESKTOP_LICENSING. Does not mint entitlement tokens.
"""

from app.oauth.router import router

__all__ = ["router"]
