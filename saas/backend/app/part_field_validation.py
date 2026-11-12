"""Shared rules for Parts master part number and description."""

from __future__ import annotations

# Allowed in part descriptions besides letters/digits (Excel uses spaces and hyphens).
_DESC_PUNCT = frozenset(" -./()&+")


def sanitize_part_master_alnum_upper(value: str | None) -> str:
    """Keep only ASCII letters and digits; uppercase. Empty string if nothing remains.

    Use for **part numbers** only — not descriptions (spaces would be stripped).
    """
    if value is None:
        return ""
    return "".join(c for c in str(value).upper() if c.isascii() and c.isalnum())


def sanitize_part_master_description(value: str | None) -> str:
    """Uppercase description: keep letters, digits, spaces, and common punctuation.

    Collapses repeated whitespace. Empty string if nothing remains.
    """
    if value is None:
        return ""
    chars: list[str] = []
    for c in str(value).upper():
        if not c.isascii():
            continue
        if c.isalnum() or c in _DESC_PUNCT:
            chars.append(" " if c.isspace() else c)
    return " ".join("".join(chars).split())
