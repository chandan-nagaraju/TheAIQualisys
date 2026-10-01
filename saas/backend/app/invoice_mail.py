"""Normalize company accounts / CC emails for tax-invoice delivery."""

from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException, status

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


def normalize_invoice_email(raw: str | None) -> str | None:
    s = (raw or "").strip().lower()
    if not s:
        return None
    if not _EMAIL.match(s):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid email address: {raw}")
    return s


def normalize_cc_emails(raw: Any, *, exclude: str | None = None) -> list[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        parts = re.split(r"[\s,;]+", raw.strip())
    elif isinstance(raw, (list, tuple)):
        parts = [str(p) for p in raw]
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CC emails must be a list")
    skip = (exclude or "").strip().lower() or None
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        email = normalize_invoice_email(part) if str(part).strip() else None
        if not email or email in seen or email == skip:
            continue
        seen.add(email)
        out.append(email)
        if len(out) > 20:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At most 20 CC email addresses")
    return out


def stored_invoice_mail(accounts: str | None, cc: Any) -> tuple[str | None, list[str]]:
    to = normalize_invoice_email(accounts)
    return to, normalize_cc_emails(cc, exclude=to)
