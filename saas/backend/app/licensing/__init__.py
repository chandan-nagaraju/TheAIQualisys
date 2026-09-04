"""Desktop product licensing — separate from FIR/QMS subscriptions.

Phase 1 foundation + corrective patch: schema, Fernet-only key encryption,
1:1:1 binding helpers, feature-flagged routers. Machine HTTP APIs remain stubs
until Phase 7.
"""

from __future__ import annotations

from app.licensing import models as licensing_models  # noqa: F401 — register ORM tables

__all__ = ["licensing_models"]
