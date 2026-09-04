"""Desktop product licensing — separate from FIR/QMS subscriptions.

Phase 1 foundation: schema models, secure key helpers, feature-flagged routers.
Machine activate/validate/refresh APIs are stubs until Phase 7.
"""

from __future__ import annotations

from app.licensing import models as licensing_models  # noqa: F401 — register ORM tables

__all__ = ["licensing_models"]
