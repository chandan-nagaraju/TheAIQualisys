"""Expand CORS allow-lists with common variants so browsers always match (e.g. apex ⟷ www)."""

from __future__ import annotations

from urllib.parse import urlparse, urlunparse


def expand_cors_origins(entries: list[str]) -> list[str]:
    """
    For each http(s) origin, also add:
    - `www.example.com` when only `example.com` is listed (two labels, not localhost).
    - `example.com` when only `www.example.com` is listed.

    Skips localhost / 127.0.0.1 and non-URL entries. Dedupes while preserving order.
    """
    out: list[str] = []
    seen: set[str] = set()

    def add(u: str) -> None:
        u = (u or "").strip().rstrip("/")
        if not u or u in seen:
            return
        seen.add(u)
        out.append(u)

    for raw in entries:
        raw = (raw or "").strip()
        if not raw:
            continue
        add(raw.rstrip("/"))
        parsed = urlparse(raw)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            continue
        netloc = parsed.netloc.split("@")[-1]
        hostname = netloc.split(":")[0].lower()
        if hostname in ("localhost", "127.0.0.1"):
            continue
        labels = hostname.split(".")
        has_port = ":" in netloc
        port_suffix = ":" + netloc.rsplit(":", 1)[-1] if has_port else ""

        if hostname.startswith("www."):
            apex_host = hostname[4:]
            if apex_host:
                alt_netloc = apex_host + port_suffix
                add(urlunparse((parsed.scheme, alt_netloc, "", "", "", "")).rstrip("/"))
        elif len(labels) == 2:
            alt_netloc = "www." + hostname + port_suffix
            add(urlunparse((parsed.scheme, alt_netloc, "", "", "", "")).rstrip("/"))

    return out
