"""Normalize company accounts / CC emails for tax-invoice delivery."""

from __future__ import annotations

import json
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


def _cc_parts(raw: Any) -> list[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        s = raw.strip()
        if s.startswith("[") or s.startswith("{"):
            try:
                parsed = json.loads(s)
            except json.JSONDecodeError:
                parsed = None
            if parsed is not None:
                return _cc_parts(parsed)
        return [p for p in re.split(r"[\s,;]+", s) if p]
    if isinstance(raw, dict):
        return [str(v) for v in raw.values()]
    if isinstance(raw, (list, tuple)):
        out: list[str] = []
        for p in raw:
            out.extend(_cc_parts(p) if not isinstance(p, str) else [p])
        return out
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CC emails must be a list")


def normalize_cc_emails(raw: Any, *, exclude: str | None = None) -> list[str]:
    skip = (exclude or "").strip().lower() or None
    out: list[str] = []
    seen: set[str] = set()
    for part in _cc_parts(raw):
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
