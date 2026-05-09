"""Shared rules for Parts master part number and description (A–Z and 0–9 only, uppercase)."""

from __future__ import annotations


def sanitize_part_master_alnum_upper(value: str | None) -> str:
    """Keep only ASCII letters and digits; uppercase. Empty string if nothing remains."""
    if value is None:
        return ""
    return "".join(c for c in str(value).upper() if c.isascii() and c.isalnum())
